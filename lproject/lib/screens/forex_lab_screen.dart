import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';

class ForexLabScreen extends StatefulWidget {
  const ForexLabScreen({super.key});

  @override
  State<ForexLabScreen> createState() => _ForexLabScreenState();
}

class _ForexLabScreenState extends State<ForexLabScreen> {
  static const _pairs = [
    _ForexPair('EUR/USD', 'Major', 'London + New York', 'Tight spread, high liquidity'),
    _ForexPair('GBP/USD', 'Major', 'London + New York', 'More volatile than EUR/USD'),
    _ForexPair('USD/JPY', 'Major', 'Tokyo + New York', 'Sensitive to rates and risk mood'),
    _ForexPair('EUR/GBP', 'Cross', 'London', 'Lower movement, useful for UK/EU view'),
    _ForexPair('AUD/USD', 'Commodity', 'Asia + New York', 'Risk-sensitive commodity pair'),
    _ForexPair('USD/CHF', 'Safe haven', 'London + New York', 'Defensive dollar pair'),
    _ForexPair('GBP/JPY', 'Volatile cross', 'London + Tokyo', 'Fast-moving; practice only'),
  ];

  int _riskBps = 50;
  int _minStrength = 78;
  String _timeframe = '15m';
  ForexSummary? _summary;
  List<ForexPosition> _positions = const [];
  bool _loading = true;
  bool _savingTrade = false;
  String? _error;

  double get _balance => _summary?.demoBalance ?? 5000;
  double get _riskAmount => _summary?.riskAmount ?? (_balance * (_riskBps / 10000));

  @override
  void initState() {
    super.initState();
    _loadSummary();
  }

  Future<void> _loadSummary() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final headers = {'device-id': DeviceService.instance.deviceId};
      final results = await Future.wait([
        http.get(Uri.parse(ApiConfig.forexSummary), headers: headers),
        http.get(Uri.parse(ApiConfig.forexPositions), headers: headers),
      ]);
      final res = results[0];
      final positionsRes = results[1];
      if (res.statusCode == 200) {
        final summary = ForexSummary.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
        final positions = positionsRes.statusCode == 200
            ? (jsonDecode(positionsRes.body) as List)
                .map((item) => ForexPosition.fromJson(item as Map<String, dynamic>))
                .toList()
            : <ForexPosition>[];
        setState(() {
          _summary = summary;
          _positions = positions;
          _riskBps = summary.riskBps;
          _minStrength = summary.minSignalStrength;
        });
      } else {
        setState(() => _error = 'Forex summary failed (${res.statusCode})');
      }
    } catch (_) {
      setState(() => _error = 'Forex backend unavailable.');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _takePracticeTrade(ForexSignal signal) async {
    if (signal.direction == 'NO_TRADE' || _savingTrade) return;
    setState(() => _savingTrade = true);
    try {
      final res = await http.post(
        Uri.parse(ApiConfig.forexPositions),
        headers: {
          'device-id': DeviceService.instance.deviceId,
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'pair': signal.pair,
          'direction': signal.direction,
          'entry_price': signal.entry,
          'stop_loss': signal.stopLoss,
          'take_profit': signal.takeProfit,
          'risk_amount': signal.riskAmount,
          'position_units': signal.positionUnits,
          'timeframe': signal.timeframe,
        }),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${signal.pair} practice trade saved.')),
        );
        await _loadSummary();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save practice trade (${res.statusCode}).')),
        );
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Forex backend unavailable.')),
      );
    } finally {
      if (mounted) setState(() => _savingTrade = false);
    }
  }

  Future<void> _closePracticeTrade(ForexPosition position) async {
    try {
      final res = await http.post(
        Uri.parse('${ApiConfig.forexPositions}/${position.id}/close'),
        headers: {
          'device-id': DeviceService.instance.deviceId,
          'Content-Type': 'application/json',
        },
        body: jsonEncode({}),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${position.pair} practice trade closed.')),
        );
        await _loadSummary();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not close practice trade (${res.statusCode}).')),
        );
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Forex backend unavailable.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('FOREX LAB',
            style: GoogleFonts.orbitron(
                color: AppColors.cyan, fontWeight: FontWeight.w700, fontSize: 15)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, size: 20),
            tooltip: 'Refresh',
            onPressed: () {
              _loadSummary();
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 28),
        children: [
          _StatusPanel(
            balance: _balance,
            riskAmount: _riskAmount,
            minStrength: _minStrength,
            timeframe: _timeframe,
          ),
          const SizedBox(height: 12),
          _RiskControls(
            riskBps: _riskBps,
            minStrength: _minStrength,
            timeframe: _timeframe,
            onRiskChanged: (value) => setState(() => _riskBps = value.round()),
            onStrengthChanged: (value) => setState(() => _minStrength = value.round()),
            onTimeframeChanged: (value) => setState(() => _timeframe = value),
          ),
          const SizedBox(height: 12),
          _ConnectionPanel(summary: _summary),
          const SizedBox(height: 12),
          _OpenForexPositions(
            positions: _positions,
            onClose: _closePracticeTrade,
          ),
          const SizedBox(height: 12),
          Text('Practice signals',
              style: GoogleFonts.orbitron(
                  color: AppColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: CircularProgressIndicator(color: AppColors.cyan)),
            )
          else if (_error != null)
            _InlineError(message: _error!, onRetry: _loadSummary)
          else
            ...(_summary?.signals ?? []).map((signal) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _SignalTile(
                    signal: signal,
                    saving: _savingTrade,
                    onTakeTrade: () => _takePracticeTrade(signal),
                  ),
                )),
          const SizedBox(height: 4),
          Text('Watchlist',
              style: GoogleFonts.orbitron(
                  color: AppColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          ..._pairs.map((pair) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _PairTile(pair: pair),
              )),
        ],
      ),
    );
  }
}

class _StatusPanel extends StatelessWidget {
  final double balance;
  final double riskAmount;
  final int minStrength;
  final String timeframe;

  const _StatusPanel({
    required this.balance,
    required this.riskAmount,
    required this.minStrength,
    required this.timeframe,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.cyan.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const _ForexIcon(),
              const SizedBox(width: 10),
              Expanded(
                child: Text('Practice CFD mode',
                    style: GoogleFonts.orbitron(
                        color: AppColors.textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w700)),
              ),
              const _ModeBadge(label: 'DEMO', color: AppColors.cyan),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(child: _Metric(label: 'Balance', value: '£${balance.toStringAsFixed(0)}')),
              Expanded(child: _Metric(label: 'Risk/trade', value: '£${riskAmount.toStringAsFixed(0)}')),
              Expanded(child: _Metric(label: 'Signal gate', value: '$minStrength+')),
              Expanded(child: _Metric(label: 'Frame', value: timeframe)),
            ],
          ),
        ],
      ),
    );
  }
}

class _ForexIcon extends StatelessWidget {
  const _ForexIcon();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 34,
      height: 34,
      decoration: BoxDecoration(
        color: AppColors.cyan.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Icon(Icons.currency_exchange, color: AppColors.cyan, size: 18),
    );
  }
}

class _RiskControls extends StatelessWidget {
  final int riskBps;
  final int minStrength;
  final String timeframe;
  final ValueChanged<double> onRiskChanged;
  final ValueChanged<double> onStrengthChanged;
  final ValueChanged<String> onTimeframeChanged;

  const _RiskControls({
    required this.riskBps,
    required this.minStrength,
    required this.timeframe,
    required this.onRiskChanged,
    required this.onStrengthChanged,
    required this.onTimeframeChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SliderRow(
            label: 'Risk per practice trade',
            value: riskBps / 100,
            suffix: '%',
            min: 0.25,
            max: 1.0,
            divisions: 3,
            onChanged: (value) => onRiskChanged(value * 100),
          ),
          const SizedBox(height: 12),
          _SliderRow(
            label: 'Minimum signal strength',
            value: minStrength.toDouble(),
            suffix: '',
            min: 70,
            max: 90,
            divisions: 20,
            onChanged: onStrengthChanged,
          ),
          const SizedBox(height: 12),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: '15m', label: Text('15m')),
              ButtonSegment(value: '1h', label: Text('1h')),
              ButtonSegment(value: '4h', label: Text('4h')),
            ],
            selected: {timeframe},
            onSelectionChanged: (values) => onTimeframeChanged(values.first),
            style: ButtonStyle(
              visualDensity: VisualDensity.compact,
              backgroundColor: WidgetStateProperty.resolveWith(
                (states) => states.contains(WidgetState.selected)
                    ? AppColors.cyan.withValues(alpha: 0.18)
                    : AppColors.surfaceHigh,
              ),
              foregroundColor: WidgetStateProperty.all(AppColors.textPrimary),
              side: WidgetStateProperty.all(const BorderSide(color: AppColors.border)),
            ),
          ),
        ],
      ),
    );
  }
}

class _ConnectionPanel extends StatelessWidget {
  final ForexSummary? summary;

  const _ConnectionPanel({required this.summary});

  @override
  Widget build(BuildContext context) {
    final connected = summary?.connected ?? false;
    final provider = (summary?.provider ?? 'mock').toUpperCase();
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.orange.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(connected ? Icons.link : Icons.link_off,
              color: connected ? AppColors.green : AppColors.orange, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(connected ? '$provider demo connected' : 'No forex broker connected',
                    style: GoogleFonts.dmSans(
                        color: AppColors.textPrimary, fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(
                    connected
                        ? 'Forex Lab is still practice-only until live trading is explicitly enabled.'
                        : 'Mock signals are shown until an IG demo connector is configured.',
                    style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SignalTile extends StatelessWidget {
  final ForexSignal signal;
  final bool saving;
  final VoidCallback onTakeTrade;

  const _SignalTile({
    required this.signal,
    required this.saving,
    required this.onTakeTrade,
  });

  @override
  Widget build(BuildContext context) {
    final color = signal.direction == 'LONG'
        ? AppColors.green
        : signal.direction == 'SHORT'
            ? AppColors.pink
            : AppColors.inactive;
    return Container(
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(signal.pair,
                  style: GoogleFonts.orbitron(
                      color: AppColors.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              _ModeBadge(label: signal.direction, color: color),
              const Spacer(),
              Text('${signal.strength}/100',
                  style: GoogleFonts.dmSans(color: color, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: _Metric(label: 'Entry', value: signal.entry.toStringAsFixed(5))),
              Expanded(child: _Metric(label: 'Stop', value: signal.stopLoss.toStringAsFixed(5))),
              Expanded(child: _Metric(label: 'Target', value: signal.takeProfit.toStringAsFixed(5))),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: _Metric(label: 'Risk', value: '£${signal.riskAmount.toStringAsFixed(0)}')),
              Expanded(child: _Metric(label: 'Units', value: signal.positionUnits.toString())),
              Expanded(child: _Metric(label: 'R:R', value: signal.riskReward.toStringAsFixed(1))),
            ],
          ),
          const SizedBox(height: 8),
          Text(signal.rationale,
              style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
          if (signal.direction != 'NO_TRADE') ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: saving ? null : onTakeTrade,
                icon: const Icon(Icons.add_chart, size: 17),
                label: const Text('I took this practice trade'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: color,
                  side: BorderSide(color: color.withValues(alpha: 0.45)),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _OpenForexPositions extends StatelessWidget {
  final List<ForexPosition> positions;
  final ValueChanged<ForexPosition> onClose;

  const _OpenForexPositions({
    required this.positions,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    final open = positions.where((pos) => pos.status == 'open').toList();
    if (open.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            const Icon(Icons.playlist_add_check, color: AppColors.textMuted, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text('No open forex practice trades',
                  style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Open practice trades',
            style: GoogleFonts.orbitron(
                color: AppColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        ...open.map((pos) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _ForexPositionTile(
                position: pos,
                onClose: () => onClose(pos),
              ),
            )),
      ],
    );
  }
}

class _ForexPositionTile extends StatelessWidget {
  final ForexPosition position;
  final VoidCallback onClose;

  const _ForexPositionTile({
    required this.position,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    final positive = (position.currentPnl ?? 0) >= 0;
    final statusColor = _statusColor(position.assistantStatus, positive);
    return Container(
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: statusColor.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(position.pair,
                  style: GoogleFonts.orbitron(
                      color: AppColors.textPrimary,
                      fontSize: 13,
                      fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              _ModeBadge(label: position.direction, color: position.direction == 'LONG' ? AppColors.green : AppColors.pink),
              const Spacer(),
              Text(
                position.currentPnl == null ? 'Tracking' : '£${position.currentPnl!.toStringAsFixed(2)}',
                style: GoogleFonts.dmSans(color: statusColor, fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: statusColor.withValues(alpha: 0.25)),
            ),
            child: Row(
              children: [
                Icon(_statusIcon(position.assistantStatus), color: statusColor, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(_statusLabel(position.assistantStatus),
                          style: GoogleFonts.dmSans(
                              color: statusColor, fontWeight: FontWeight.w800, fontSize: 12)),
                      const SizedBox(height: 2),
                      Text(position.assistantMessage,
                          style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 11)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: _Metric(label: 'Entry', value: position.entryPrice.toStringAsFixed(5))),
              Expanded(child: _Metric(label: 'Now', value: position.currentPrice?.toStringAsFixed(5) ?? '-')),
              Expanded(child: _Metric(label: 'Risk', value: '£${position.riskAmount.toStringAsFixed(0)}')),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onClose,
              icon: const Icon(Icons.check_circle_outline, size: 17),
              label: const Text('Close practice trade'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.textPrimary,
                side: const BorderSide(color: AppColors.border),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _statusColor(String status, bool positive) {
    switch (status) {
      case 'TAKE_PROFIT':
      case 'PROTECT_PROFIT':
        return AppColors.green;
      case 'CUT_LOSS':
        return AppColors.pink;
      case 'HOLD_CAUTION':
        return AppColors.orange;
      default:
        return positive ? AppColors.cyan : AppColors.textMuted;
    }
  }

  IconData _statusIcon(String status) {
    switch (status) {
      case 'TAKE_PROFIT':
        return Icons.flag_circle_outlined;
      case 'PROTECT_PROFIT':
        return Icons.shield_outlined;
      case 'CUT_LOSS':
        return Icons.warning_amber_rounded;
      case 'HOLD_CAUTION':
        return Icons.visibility_outlined;
      default:
        return Icons.timelapse;
    }
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'TAKE_PROFIT':
        return 'TAKE PROFIT';
      case 'PROTECT_PROFIT':
        return 'PROTECT PROFIT';
      case 'CUT_LOSS':
        return 'CUT LOSS';
      case 'HOLD_CAUTION':
        return 'HOLD WITH CAUTION';
      case 'CLOSED':
        return 'CLOSED';
      default:
        return 'HOLD';
    }
  }
}

class _InlineError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _InlineError({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.pink.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppColors.pink, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(message, style: GoogleFonts.dmSans(color: AppColors.textMuted))),
          IconButton(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh, size: 18),
            tooltip: 'Retry',
          ),
        ],
      ),
    );
  }
}

class _PairTile extends StatelessWidget {
  final _ForexPair pair;

  const _PairTile({required this.pair});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 50,
            decoration: BoxDecoration(
              color: AppColors.cyan,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(pair.symbol,
                        style: GoogleFonts.orbitron(
                            color: AppColors.textPrimary,
                            fontSize: 14,
                            fontWeight: FontWeight.w700)),
                    const SizedBox(width: 8),
                    _ModeBadge(label: pair.kind, color: AppColors.orange),
                  ],
                ),
                const SizedBox(height: 5),
                Text(pair.note,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
                const SizedBox(height: 4),
                Text(pair.session,
                    style: GoogleFonts.dmSans(
                        color: AppColors.textMuted.withValues(alpha: 0.75), fontSize: 11)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          const Icon(Icons.lock_outline, color: AppColors.inactive, size: 18),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;

  const _Metric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 11)),
        const SizedBox(height: 3),
        Text(value,
            style: GoogleFonts.dmSans(
                color: AppColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _SliderRow extends StatelessWidget {
  final String label;
  final double value;
  final String suffix;
  final double min;
  final double max;
  final int divisions;
  final ValueChanged<double> onChanged;

  const _SliderRow({
    required this.label,
    required this.value,
    required this.suffix,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final display = suffix == '%' ? value.toStringAsFixed(2) : value.round().toString();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(label,
                  style: GoogleFonts.dmSans(
                      color: AppColors.textPrimary, fontWeight: FontWeight.w600)),
            ),
            Text('$display$suffix',
                style: GoogleFonts.dmSans(color: AppColors.cyan, fontWeight: FontWeight.w700)),
          ],
        ),
        Slider(
          value: value,
          min: min,
          max: max,
          divisions: divisions,
          activeColor: AppColors.cyan,
          inactiveColor: AppColors.border,
          onChanged: onChanged,
        ),
      ],
    );
  }
}

class _ModeBadge extends StatelessWidget {
  final String label;
  final Color color;

  const _ModeBadge({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(label,
          style: GoogleFonts.dmSans(
              color: color, fontSize: 10, fontWeight: FontWeight.w700)),
    );
  }
}

class _ForexPair {
  final String symbol;
  final String kind;
  final String session;
  final String note;

  const _ForexPair(this.symbol, this.kind, this.session, this.note);
}

class ForexSummary {
  final String provider;
  final bool connected;
  final double demoBalance;
  final int riskBps;
  final double riskAmount;
  final int minSignalStrength;
  final List<ForexSignal> signals;

  const ForexSummary({
    required this.provider,
    required this.connected,
    required this.demoBalance,
    required this.riskBps,
    required this.riskAmount,
    required this.minSignalStrength,
    required this.signals,
  });

  factory ForexSummary.fromJson(Map<String, dynamic> json) => ForexSummary(
        provider: json['provider'] as String,
        connected: json['connected'] as bool,
        demoBalance: (json['demo_balance'] as num).toDouble(),
        riskBps: (json['risk_bps'] as num).toInt(),
        riskAmount: (json['risk_amount'] as num).toDouble(),
        minSignalStrength: (json['min_signal_strength'] as num).toInt(),
        signals: (json['signals'] as List)
            .map((item) => ForexSignal.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}

class ForexSignal {
  final String pair;
  final String direction;
  final int strength;
  final String timeframe;
  final double entry;
  final double stopLoss;
  final double takeProfit;
  final double riskReward;
  final double riskAmount;
  final int positionUnits;
  final String rationale;

  const ForexSignal({
    required this.pair,
    required this.direction,
    required this.strength,
    required this.timeframe,
    required this.entry,
    required this.stopLoss,
    required this.takeProfit,
    required this.riskReward,
    required this.riskAmount,
    required this.positionUnits,
    required this.rationale,
  });

  factory ForexSignal.fromJson(Map<String, dynamic> json) => ForexSignal(
        pair: json['pair'] as String,
        direction: json['direction'] as String,
        strength: (json['strength'] as num).toInt(),
        timeframe: json['timeframe'] as String,
        entry: (json['entry'] as num).toDouble(),
        stopLoss: (json['stop_loss'] as num).toDouble(),
        takeProfit: (json['take_profit'] as num).toDouble(),
        riskReward: (json['risk_reward'] as num).toDouble(),
        riskAmount: (json['risk_amount'] as num).toDouble(),
        positionUnits: (json['position_units'] as num).toInt(),
        rationale: json['rationale'] as String,
      );
}

class ForexPosition {
  final String id;
  final String pair;
  final String direction;
  final double entryPrice;
  final double stopLoss;
  final double takeProfit;
  final double riskAmount;
  final int positionUnits;
  final String timeframe;
  final String status;
  final double? currentPrice;
  final double? currentPnl;
  final double? currentPnlPct;
  final String assistantStatus;
  final String assistantMessage;

  const ForexPosition({
    required this.id,
    required this.pair,
    required this.direction,
    required this.entryPrice,
    required this.stopLoss,
    required this.takeProfit,
    required this.riskAmount,
    required this.positionUnits,
    required this.timeframe,
    required this.status,
    required this.currentPrice,
    required this.currentPnl,
    required this.currentPnlPct,
    required this.assistantStatus,
    required this.assistantMessage,
  });

  factory ForexPosition.fromJson(Map<String, dynamic> json) => ForexPosition(
        id: json['id'] as String,
        pair: json['pair'] as String,
        direction: json['direction'] as String,
        entryPrice: (json['entry_price'] as num).toDouble(),
        stopLoss: (json['stop_loss'] as num).toDouble(),
        takeProfit: (json['take_profit'] as num).toDouble(),
        riskAmount: (json['risk_amount'] as num).toDouble(),
        positionUnits: (json['position_units'] as num).toInt(),
        timeframe: json['timeframe'] as String,
        status: json['status'] as String,
        currentPrice: (json['current_price'] as num?)?.toDouble(),
        currentPnl: (json['current_pnl'] as num?)?.toDouble(),
        currentPnlPct: (json['current_pnl_pct'] as num?)?.toDouble(),
        assistantStatus: json['assistant_status'] as String? ?? 'HOLD',
        assistantMessage: json['assistant_message'] as String? ?? 'Trade is active.',
      );
}
