class PieSlice {
  final String ticker;
  final String name;
  final String instrumentType;
  final String marketTheme;
  final double allocationPercent;
  final double amount;
  final double opportunityScore;
  final int opportunityStrength;
  final String strengthLabel;
  final String rationale;

  const PieSlice({
    required this.ticker,
    required this.name,
    required this.instrumentType,
    required this.marketTheme,
    required this.allocationPercent,
    required this.amount,
    required this.opportunityScore,
    required this.opportunityStrength,
    required this.strengthLabel,
    required this.rationale,
  });

  factory PieSlice.fromJson(Map<String, dynamic> j) => PieSlice(
        ticker: j['ticker'] as String,
        name: j['name'] as String,
        instrumentType: j['instrument_type'] as String,
        marketTheme: j['market_theme'] as String,
        allocationPercent: (j['allocation_percent'] as num).toDouble(),
        amount: (j['amount'] as num).toDouble(),
        opportunityScore: (j['opportunity_score'] as num).toDouble(),
        opportunityStrength:
            (j['opportunity_strength'] as num?)?.toInt() ??
                (j['opportunity_score'] as num).toInt(),
        strengthLabel: (j['strength_label'] as String?) ?? 'Review',
        rationale: j['rationale'] as String,
      );
}

class DataFreshness {
  final String status; // "fresh" | "stale" | "unavailable"
  final String newestDataTimestamp;
  final String oldestAllowedTimestamp;
  final List<String> staleTickers;

  const DataFreshness({
    required this.status,
    required this.newestDataTimestamp,
    required this.oldestAllowedTimestamp,
    required this.staleTickers,
  });

  factory DataFreshness.fromJson(Map<String, dynamic> j) => DataFreshness(
        status: j['status'] as String,
        newestDataTimestamp: j['newest_data_timestamp'] as String,
        oldestAllowedTimestamp: j['oldest_allowed_timestamp'] as String,
        staleTickers: List<String>.from(j['stale_tickers'] as List),
      );
}

class PieBuildResult {
  final String pieName;
  final String goal;
  final String riskLevel;
  final double totalAmount;
  final String timeHorizon;
  final List<PieSlice> slices;
  final String overallRationale;
  final String riskNote;
  final bool executable;
  final List<String> safetyFlags;
  final List<String> warnings;
  final DataFreshness dataFreshness;
  final String marketDataTimestamp;
  final String validUntil;
  final bool investOnlyVerified;
  final bool allSlicesValidated;
  final bool manualExecutionOnly;

  const PieBuildResult({
    required this.pieName,
    required this.goal,
    required this.riskLevel,
    required this.totalAmount,
    required this.timeHorizon,
    required this.slices,
    required this.overallRationale,
    required this.riskNote,
    required this.executable,
    required this.safetyFlags,
    required this.warnings,
    required this.dataFreshness,
    required this.marketDataTimestamp,
    required this.validUntil,
    required this.investOnlyVerified,
    required this.allSlicesValidated,
    required this.manualExecutionOnly,
  });

  factory PieBuildResult.fromJson(Map<String, dynamic> j) => PieBuildResult(
        pieName: j['pie_name'] as String,
        goal: j['goal'] as String,
        riskLevel: j['risk_level'] as String,
        totalAmount: (j['total_amount'] as num).toDouble(),
        timeHorizon: j['time_horizon'] as String,
        slices: (j['slices'] as List)
            .map((s) => PieSlice.fromJson(s as Map<String, dynamic>))
            .toList(),
        overallRationale: j['overall_rationale'] as String,
        riskNote: j['risk_note'] as String,
        executable: j['executable'] as bool,
        safetyFlags: List<String>.from(j['safety_flags'] as List),
        warnings: List<String>.from((j['warnings'] as List?) ?? []),
        dataFreshness: DataFreshness.fromJson(
            j['data_freshness'] as Map<String, dynamic>),
        marketDataTimestamp: j['market_data_timestamp'] as String,
        validUntil: j['valid_until'] as String,
        investOnlyVerified: j['invest_only_verified'] as bool? ?? true,
        allSlicesValidated: j['all_slices_validated'] as bool? ?? true,
        manualExecutionOnly: j['manual_execution_only'] as bool? ?? true,
      );

  String toCopyText() {
    final buf = StringBuffer();
    buf.writeln(pieName);
    buf.writeln('─' * 30);
    for (final s in slices) {
      buf.writeln('${s.allocationPercent.toStringAsFixed(1)}%  ${s.ticker}  £${s.amount.toStringAsFixed(2)}');
    }
    buf.writeln();
    buf.writeln('Total: £${totalAmount.toStringAsFixed(2)} | Risk: $riskLevel');
    return buf.toString().trim();
  }
}

class SavedPieSummary {
  final String id;
  final String pieName;
  final String riskLevel;
  final double totalAmount;
  final String createdAt;
  final List<PieSlice> slices;

  const SavedPieSummary({
    required this.id,
    required this.pieName,
    required this.riskLevel,
    required this.totalAmount,
    required this.createdAt,
    required this.slices,
  });

  factory SavedPieSummary.fromJson(Map<String, dynamic> j) => SavedPieSummary(
        id: j['id'] as String,
        pieName: j['pie_name'] as String,
        riskLevel: j['risk_level'] as String,
        totalAmount: (j['total_amount'] as num).toDouble(),
        createdAt: j['created_at'] as String,
        slices: (j['slices'] as List)
            .map((s) => PieSlice.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}
