class TradeAlert {
  final String id;
  final String ticker;
  final String action;
  final double signalScore;
  final int confidence;
  final int formulaScore;
  final int claudeConfidence;
  final int? portfolioFitScore;
  final int? weaknessScore;
  final int? drawdownRiskScore;
  final int? exposureRiskScore;
  final int actionStrength;
  final String actionLabel;
  final String scoreInterpretation;
  final String actionStrengthDisclaimer;
  final bool trading212ReviewEnabled;
  final String? t212ReviewUrl;
  final double suggestedAmount;
  final double priceAtAlert;
  final String alertTitle;
  final String alertBody;
  final String rationale;
  final String riskNote;
  final List<String> keyFactors;
  final List<String> blockingRisks;
  final DateTime expiresAt;
  final bool executable;
  final List<String> safetyFlags;
  final DateTime createdAt;

  const TradeAlert({
    required this.id,
    required this.ticker,
    required this.action,
    required this.signalScore,
    required this.confidence,
    required this.formulaScore,
    required this.claudeConfidence,
    this.portfolioFitScore,
    this.weaknessScore,
    this.drawdownRiskScore,
    this.exposureRiskScore,
    required this.actionStrength,
    required this.actionLabel,
    required this.scoreInterpretation,
    required this.actionStrengthDisclaimer,
    required this.trading212ReviewEnabled,
    this.t212ReviewUrl,
    required this.suggestedAmount,
    required this.priceAtAlert,
    required this.alertTitle,
    required this.alertBody,
    required this.rationale,
    required this.riskNote,
    required this.keyFactors,
    required this.blockingRisks,
    required this.expiresAt,
    required this.executable,
    required this.safetyFlags,
    required this.createdAt,
  });

  factory TradeAlert.fromJson(Map<String, dynamic> json) {
    return TradeAlert(
      id: json['id'] as String,
      ticker: json['ticker'] as String,
      action: json['action'] as String,
      signalScore: (json['signal_score'] as num).toDouble(),
      confidence: (json['confidence'] as num).toInt(),
      formulaScore: (json['formula_score'] as num?)?.toInt() ?? (json['signal_score'] as num).toInt(),
      claudeConfidence: (json['claude_confidence'] as num?)?.toInt() ?? (json['confidence'] as num).toInt(),
      portfolioFitScore: (json['portfolio_fit_score'] as num?)?.toInt(),
      weaknessScore: (json['weakness_score'] as num?)?.toInt(),
      drawdownRiskScore: (json['drawdown_risk_score'] as num?)?.toInt(),
      exposureRiskScore: (json['exposure_risk_score'] as num?)?.toInt(),
      actionStrength: (json['action_strength'] as num?)?.toInt() ?? 0,
      actionLabel: (json['action_label'] as String?) ?? 'Ignore',
      scoreInterpretation: (json['score_interpretation'] as String?) ?? '',
      actionStrengthDisclaimer: (json['action_strength_disclaimer'] as String?) ?? '',
      trading212ReviewEnabled: (json['trading212_review_enabled'] as bool?) ?? false,
      t212ReviewUrl: json['t212_review_url'] as String?,
      suggestedAmount: (json['suggested_amount'] as num).toDouble(),
      priceAtAlert: (json['price_at_alert'] as num).toDouble(),
      alertTitle: json['alert_title'] as String,
      alertBody: json['alert_body'] as String,
      rationale: json['rationale'] as String,
      riskNote: json['risk_note'] as String,
      keyFactors: List<String>.from(json['key_factors'] as List),
      blockingRisks: List<String>.from(json['blocking_risks'] as List),
      expiresAt: DateTime.parse(json['expires_at'] as String),
      executable: json['executable'] as bool,
      safetyFlags: List<String>.from(json['safety_flags'] as List),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  bool get isExpired => DateTime.now().isAfter(expiresAt);
}

class SignalOutcome {
  final String alertId;
  final String ticker;
  final String action;
  final double formulaScore;
  final int claudeConfidence;
  final int actionStrength;
  final String actionLabel;
  final double priceAtAlert;
  final double suggestedAmount;
  final String? outcome; // "took_trade" | "ignored" | "watching"
  final double? manualEntryPrice;
  final double? manualExitPrice;
  final double? manualAmount;
  final double? realisedPnl;
  final String? tradeNotes;
  final double? price1h;
  final double? price1d;
  final double? price5d;
  final double? maxGain1d;
  final double? maxDrawdown1d;
  final double claudeCostEstimate;
  final DateTime createdAt;

  const SignalOutcome({
    required this.alertId,
    required this.ticker,
    required this.action,
    required this.formulaScore,
    required this.claudeConfidence,
    required this.actionStrength,
    required this.actionLabel,
    required this.priceAtAlert,
    required this.suggestedAmount,
    this.outcome,
    this.manualEntryPrice,
    this.manualExitPrice,
    this.manualAmount,
    this.realisedPnl,
    this.tradeNotes,
    this.price1h,
    this.price1d,
    this.price5d,
    this.maxGain1d,
    this.maxDrawdown1d,
    required this.claudeCostEstimate,
    required this.createdAt,
  });

  factory SignalOutcome.fromJson(Map<String, dynamic> j) => SignalOutcome(
        alertId: j['alert_id'] as String,
        ticker: j['ticker'] as String,
        action: j['action'] as String,
        formulaScore: (j['formula_score'] as num).toDouble(),
        claudeConfidence: (j['claude_confidence'] as num).toInt(),
        actionStrength: (j['action_strength'] as num?)?.toInt() ?? 0,
        actionLabel: (j['action_label'] as String?) ?? 'Ignore',
        priceAtAlert: (j['price_at_alert'] as num).toDouble(),
        suggestedAmount: (j['suggested_amount'] as num).toDouble(),
        outcome: j['outcome'] as String?,
        manualEntryPrice: (j['manual_entry_price'] as num?)?.toDouble(),
        manualExitPrice: (j['manual_exit_price'] as num?)?.toDouble(),
        manualAmount: (j['manual_amount'] as num?)?.toDouble(),
        realisedPnl: (j['realised_pnl'] as num?)?.toDouble(),
        tradeNotes: j['trade_notes'] as String?,
        price1h: (j['price_1h'] as num?)?.toDouble(),
        price1d: (j['price_1d'] as num?)?.toDouble(),
        price5d: (j['price_5d'] as num?)?.toDouble(),
        maxGain1d: (j['max_gain_1d'] as num?)?.toDouble(),
        maxDrawdown1d: (j['max_drawdown_1d'] as num?)?.toDouble(),
        claudeCostEstimate: (j['claude_cost_estimate'] as num).toDouble(),
        createdAt: DateTime.parse(j['created_at'] as String),
      );
}
