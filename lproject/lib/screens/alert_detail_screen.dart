import 'dart:convert';
import 'package:android_intent_plus/android_intent.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import '../config/api_config.dart';
import '../models/alert_model.dart';
import '../services/device_service.dart';

class AlertDetailScreen extends StatefulWidget {
  final String alertId;
  const AlertDetailScreen({super.key, required this.alertId});

  @override
  State<AlertDetailScreen> createState() => _AlertDetailScreenState();
}

class _AlertDetailScreenState extends State<AlertDetailScreen> {
  TradeAlert? _alert;
  SignalOutcome? _outcome;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadAlert();
  }

  Future<void> _loadAlert() async {
    try {
      final alertFuture = http.get(
        Uri.parse('${ApiConfig.alerts}/${widget.alertId}'),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      final outcomeFuture = http.get(
        Uri.parse('${ApiConfig.alerts}/${widget.alertId}/outcome'),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      final results = await Future.wait([alertFuture, outcomeFuture]);
      if (!mounted) return;

      if (results[0].statusCode == 200) {
        setState(() {
          _alert = TradeAlert.fromJson(
              jsonDecode(results[0].body) as Map<String, dynamic>);
        });
      } else {
        setState(() => _error = 'Alert not found.');
      }
      if (results[1].statusCode == 200) {
        setState(() {
          _outcome = SignalOutcome.fromJson(
              jsonDecode(results[1].body) as Map<String, dynamic>);
        });
      }
    } catch (_) {
      setState(() => _error = 'Connection failed.');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _openT212(TradeAlert alert) async {
    await Clipboard.setData(ClipboardData(text: alert.ticker));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${alert.ticker} copied — paste in T212 search'),
          duration: const Duration(seconds: 4),
        ),
      );
    }
    const package = 'com.avuscapital.trading212';
    final intent = AndroidIntent(
      action: 'android.intent.action.MAIN',
      package: package,
      componentName: 'com.avuscapital.trading212.MainActivity',
      flags: const <int>[0x10000000], // FLAG_ACTIVITY_NEW_TASK
    );
    try {
      await intent.launch();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open Trading 212')),
        );
      }
    }
  }

  void _copyOrderDetails(TradeAlert alert) {
    final text = '''
Order Details
─────────────
Ticker:           ${alert.ticker}
Action:           ${alert.action}
Suggested Amount: £${alert.suggestedAmount.toStringAsFixed(2)}
Price at Alert:   £${alert.priceAtAlert.toStringAsFixed(4)}
Rationale:        ${alert.rationale}
Risk Note:        ${alert.riskNote}
'''.trim();

    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Order details copied to clipboard')),
    );
  }

  Future<void> _recordOutcome(String outcomeType,
      {double? entryPrice, double? amount, String? notes}) async {
    final body = <String, dynamic>{'outcome': outcomeType};
    if (entryPrice != null) body['manual_entry_price'] = entryPrice;
    if (amount != null) body['manual_amount'] = amount;
    if (notes != null) body['trade_notes'] = notes;

    try {
      final res = await http.post(
        Uri.parse('${ApiConfig.alerts}/${widget.alertId}/outcome'),
        headers: {
          'Content-Type': 'application/json',
          'device-id': DeviceService.instance.deviceId,
        },
        body: jsonEncode(body),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() {
          _outcome = SignalOutcome.fromJson(
              jsonDecode(res.body) as Map<String, dynamic>);
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Marked as $outcomeType')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to save outcome')),
        );
      }
    }
  }

  Future<void> _closeTrade() async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => _CloseTradeDialog(
        ticker: _alert!.ticker,
        entryPrice: _outcome?.manualEntryPrice,
      ),
    );
    if (result == null || !mounted) return;

    try {
      final res = await http.patch(
        Uri.parse('${ApiConfig.alerts}/${widget.alertId}/outcome/close'),
        headers: {
          'Content-Type': 'application/json',
          'device-id': DeviceService.instance.deviceId,
        },
        body: jsonEncode(result),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() {
          _outcome = SignalOutcome.fromJson(
              jsonDecode(res.body) as Map<String, dynamic>);
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Trade closed and P&L recorded')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to close trade')),
        );
      }
    }
  }

  Future<void> _showTookTradeDialog() async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => _TookTradeDialog(
        ticker: _alert!.ticker,
        suggestedAmount: _alert!.suggestedAmount,
        priceAtAlert: _alert!.priceAtAlert,
      ),
    );
    if (result == null) return;
    await _recordOutcome(
      'took_trade',
      entryPrice: result['entry_price'] as double?,
      amount: result['amount'] as double?,
      notes: result['notes'] as String?,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Alert Detail')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return Center(child: Text(_error!));
    if (_alert == null) return const SizedBox.shrink();
    return _AlertDetail(
      alert: _alert!,
      outcome: _outcome,
      onOpenT212: () => _openT212(_alert!),
      onCopy: () => _copyOrderDetails(_alert!),
      onTookTrade: _showTookTradeDialog,
      onIgnored: () => _recordOutcome('ignored'),
      onWatching: () => _recordOutcome('watching'),
      onCloseTrade: _closeTrade,
    );
  }
}

// ── Main detail view ──────────────────────────────────────────────────────────

class _AlertDetail extends StatefulWidget {
  final TradeAlert alert;
  final SignalOutcome? outcome;
  final VoidCallback onOpenT212;
  final VoidCallback onCopy;
  final VoidCallback onTookTrade;
  final VoidCallback onIgnored;
  final VoidCallback onWatching;
  final VoidCallback onCloseTrade;

  const _AlertDetail({
    required this.alert,
    required this.outcome,
    required this.onOpenT212,
    required this.onCopy,
    required this.onTookTrade,
    required this.onIgnored,
    required this.onWatching,
    required this.onCloseTrade,
  });

  @override
  State<_AlertDetail> createState() => _AlertDetailState();
}

class _AlertDetailState extends State<_AlertDetail> {
  bool _showAdvanced = false;

  @override
  Widget build(BuildContext context) {
    final alert = widget.alert;
    final outcome = widget.outcome;
    final expired = alert.isExpired;
    final isBuy = alert.action == 'BUY_REVIEW';
    final isSell = alert.action == 'REVIEW_SELL';
    final canExecute = alert.trading212ReviewEnabled &&
        alert.actionStrength >= 70 &&
        (isBuy || isSell) &&
        !expired;

    final strengthColor = alert.actionStrength >= 80
        ? Colors.green
        : alert.actionStrength >= 70
            ? Colors.orange
            : Colors.grey;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── Hero header ──────────────────────────────────────────────────
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(alert.ticker,
                              style: const TextStyle(
                                  fontSize: 36, fontWeight: FontWeight.bold)),
                          if (expired)
                            const Text('Expired',
                                style: TextStyle(color: Colors.red, fontSize: 12))
                          else
                            Text(
                              'Valid until ${DateFormat('HH:mm').format(alert.expiresAt.toLocal())}',
                              style: TextStyle(color: Colors.grey[500], fontSize: 12),
                            ),
                        ],
                      ),
                      _ActionBadge(action: alert.action),
                    ],
                  ),

                  const SizedBox(height: 20),

                  // Confidence bar
                  Row(
                    children: [
                      const Text('Signal strength',
                          style: TextStyle(fontSize: 13, color: Colors.grey)),
                      const Spacer(),
                      Text('${alert.actionStrength}/100',
                          style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.bold,
                              color: strengthColor)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: alert.actionStrength / 100,
                      minHeight: 10,
                      backgroundColor: Colors.grey[200],
                      valueColor: AlwaysStoppedAnimation<Color>(strengthColor),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(alert.actionLabel,
                      style: TextStyle(
                          fontSize: 12,
                          color: strengthColor,
                          fontWeight: FontWeight.w600)),

                  const SizedBox(height: 16),

                  Row(
                    children: [
                      _StatPill(
                          label: 'Price',
                          value: '£${alert.priceAtAlert.toStringAsFixed(2)}'),
                      const SizedBox(width: 8),
                      _StatPill(
                          label: 'Suggested',
                          value: '£${alert.suggestedAmount.toStringAsFixed(0)}'),
                    ],
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),

          // ── What is this? ────────────────────────────────────────────────
          if (alert.whatIsThis.isNotEmpty)
            _InfoCard(
              icon: Icons.info_outline,
              color: Colors.blue,
              title: 'What is ${alert.ticker}?',
              body: alert.whatIsThis,
            ),

          if (alert.whatIsThis.isNotEmpty) const SizedBox(height: 8),

          // ── Why now? ─────────────────────────────────────────────────────
          _InfoCard(
            icon: Icons.insights,
            color: Colors.green,
            title: 'Why now?',
            body: alert.rationale,
          ),

          const SizedBox(height: 8),

          // ── Step-by-step (buy alerts only) ───────────────────────────────
          if (canExecute && isBuy) ...[
            _StepsCard(ticker: alert.ticker, amount: alert.suggestedAmount),
            const SizedBox(height: 8),
          ],

          // ── Step-by-step (sell alerts) ───────────────────────────────────
          if (canExecute && isSell) ...[
            _SellStepsCard(ticker: alert.ticker),
            const SizedBox(height: 8),
          ],

          // ── Key factors ──────────────────────────────────────────────────
          if (alert.keyFactors.isNotEmpty) ...[
            _BulletSection(
                title: 'What looks good',
                items: alert.keyFactors,
                color: Colors.green),
            const SizedBox(height: 8),
          ],

          // ── Risks ────────────────────────────────────────────────────────
          if (alert.blockingRisks.isNotEmpty) ...[
            _BulletSection(
                title: 'Things to be aware of',
                items: alert.blockingRisks,
                color: Colors.orange),
            const SizedBox(height: 8),
          ],

          // ── Risk note ────────────────────────────────────────────────────
          _InfoCard(
            icon: Icons.shield_outlined,
            color: Colors.orange,
            title: 'Important',
            body: alert.riskNote,
          ),

          const SizedBox(height: 8),

          // ── Advanced toggle ──────────────────────────────────────────────
          GestureDetector(
            onTap: () => setState(() => _showAdvanced = !_showAdvanced),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  _showAdvanced ? 'Hide technical details' : 'Show technical details',
                  style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                ),
                Icon(
                  _showAdvanced ? Icons.expand_less : Icons.expand_more,
                  size: 16,
                  color: Colors.grey[500],
                ),
              ],
            ),
          ),

          if (_showAdvanced) ...[
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Technical Details',
                        style: TextStyle(
                            fontWeight: FontWeight.bold, color: Colors.grey)),
                    const SizedBox(height: 10),
                    _AdvancedRow('Formula Score', '${alert.formulaScore}/100'),
                    _AdvancedRow('Claude Confidence', '${alert.claudeConfidence}/100'),
                    if (alert.portfolioFitScore != null)
                      _AdvancedRow('Portfolio Fit', '${alert.portfolioFitScore}/100'),
                    _AdvancedRow('Action Strength', '${alert.actionStrength}/100'),
                    _AdvancedRow('Signal Score', alert.signalScore.toStringAsFixed(1)),
                    if (alert.safetyFlags.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      ...alert.safetyFlags.map(
                        (f) => Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Row(
                            children: [
                              const Icon(Icons.warning_amber,
                                  color: Colors.orange, size: 14),
                              const SizedBox(width: 6),
                              Expanded(
                                  child: Text(f,
                                      style: const TextStyle(fontSize: 12))),
                            ],
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Text(
                      alert.actionStrengthDisclaimer,
                      style: const TextStyle(fontSize: 11, color: Colors.grey),
                    ),
                  ],
                ),
              ),
            ),
          ],

          const SizedBox(height: 16),

          // ── Outcome card ─────────────────────────────────────────────────
          _OutcomeCard(
            outcome: outcome,
            onTookTrade: widget.onTookTrade,
            onIgnored: widget.onIgnored,
            onWatching: widget.onWatching,
            onCloseTrade: widget.onCloseTrade,
          ),

          const SizedBox(height: 16),

          if (outcome != null &&
              (outcome.price1h != null || outcome.price1d != null)) ...[
            _PriceTrackingCard(
                outcome: outcome, priceAtAlert: alert.priceAtAlert),
            const SizedBox(height: 16),
          ],

          // ── Action buttons ───────────────────────────────────────────────
          OutlinedButton.icon(
            onPressed: widget.onCopy,
            icon: const Icon(Icons.copy, size: 16),
            label: const Text('Copy details'),
          ),

          const SizedBox(height: 10),

          ElevatedButton.icon(
            onPressed: canExecute ? widget.onOpenT212 : null,
            icon: Icon(isSell ? Icons.trending_down : Icons.open_in_new),
            label: Text(isSell ? 'Review Sell in Trading 212' : 'Open in Trading 212 to Buy'),
            style: ElevatedButton.styleFrom(
              backgroundColor: isSell ? Colors.red : Colors.green,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 16),
              disabledBackgroundColor: Colors.grey[300],
              textStyle: const TextStyle(
                  fontSize: 16, fontWeight: FontWeight.bold),
            ),
          ),

          if (!canExecute)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                expired
                    ? 'This alert has expired.'
                    : alert.action == 'WATCH'
                        ? 'Not strong enough to act on yet — watch for now.'
                        : 'Not available — safety checks did not pass.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey[500], fontSize: 12),
              ),
            ),

          const SizedBox(height: 8),
          const Text(
            'This app does not place trades. You are responsible for all decisions.',
            style: TextStyle(fontSize: 11, color: Colors.grey),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

// ── Outcome card ──────────────────────────────────────────────────────────────

class _OutcomeCard extends StatelessWidget {
  final SignalOutcome? outcome;
  final VoidCallback onTookTrade;
  final VoidCallback onIgnored;
  final VoidCallback onWatching;
  final VoidCallback onCloseTrade;

  const _OutcomeCard({
    required this.outcome,
    required this.onTookTrade,
    required this.onIgnored,
    required this.onWatching,
    required this.onCloseTrade,
  });

  @override
  Widget build(BuildContext context) {
    final current = outcome?.outcome;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('What did you do with this alert?',
                style: TextStyle(fontWeight: FontWeight.bold, color: Colors.grey)),
            const SizedBox(height: 12),
            if (current == null) ...[
              Row(
                children: [
                  Expanded(
                    child: _OutcomeButton(
                      label: 'I took this trade',
                      icon: Icons.check_circle_outline,
                      color: Colors.green,
                      onTap: onTookTrade,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _OutcomeButton(
                      label: 'I ignored this',
                      icon: Icons.cancel_outlined,
                      color: Colors.grey,
                      onTap: onIgnored,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _OutcomeButton(
                      label: 'Watching',
                      icon: Icons.visibility_outlined,
                      color: Colors.orange,
                      onTap: onWatching,
                    ),
                  ),
                ],
              ),
            ] else ...[
              _OutcomeBadge(outcome: current),
              if (current == 'took_trade') ...[
                const SizedBox(height: 8),
                if (outcome!.manualEntryPrice != null)
                  _OutcomeRow('Entry price', '£${outcome!.manualEntryPrice!.toStringAsFixed(4)}'),
                if (outcome!.manualAmount != null)
                  _OutcomeRow('Amount invested', '£${outcome!.manualAmount!.toStringAsFixed(2)}'),
                if (outcome!.realisedPnl != null)
                  _OutcomeRow(
                    'Realised P&L',
                    '£${outcome!.realisedPnl!.toStringAsFixed(2)}',
                    valueColor: (outcome!.realisedPnl! >= 0) ? Colors.green : Colors.red,
                  ),
                if (outcome!.tradeNotes != null)
                  _OutcomeRow('Notes', outcome!.tradeNotes!),
                const SizedBox(height: 8),
                if (outcome!.manualExitPrice == null)
                  OutlinedButton.icon(
                    onPressed: onCloseTrade,
                    icon: const Icon(Icons.lock_outline, size: 16),
                    label: const Text('Close trade & record P&L'),
                    style: OutlinedButton.styleFrom(foregroundColor: Colors.red),
                  ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _OutcomeButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _OutcomeButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(height: 4),
            Text(label,
                style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _OutcomeBadge extends StatelessWidget {
  final String outcome;
  const _OutcomeBadge({required this.outcome});

  @override
  Widget build(BuildContext context) {
    final (label, color, icon) = switch (outcome) {
      'took_trade' => ('Took this trade', Colors.green, Icons.check_circle),
      'ignored' => ('Ignored', Colors.grey, Icons.cancel),
      _ => ('Watching', Colors.orange, Icons.visibility),
    };
    return Row(
      children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(width: 6),
        Text(label, style: TextStyle(color: color, fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _OutcomeRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;
  const _OutcomeRow(this.label, this.value, {this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: [
          SizedBox(
            width: 120,
            child: Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ),
          Expanded(
            child: Text(value,
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: valueColor)),
          ),
        ],
      ),
    );
  }
}

// ── Price tracking card ───────────────────────────────────────────────────────

class _PriceTrackingCard extends StatelessWidget {
  final SignalOutcome outcome;
  final double priceAtAlert;
  const _PriceTrackingCard({required this.outcome, required this.priceAtAlert});

  String _pct(double? price) {
    if (price == null || priceAtAlert == 0) return '—';
    final pct = (price - priceAtAlert) / priceAtAlert * 100;
    return '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(2)}%';
  }

  Color _pctColor(double? price) {
    if (price == null || priceAtAlert == 0) return Colors.grey;
    return (price >= priceAtAlert) ? Colors.green : Colors.red;
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Price Tracking',
                style: TextStyle(fontWeight: FontWeight.bold, color: Colors.grey)),
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _PricePoint(label: '1h', pct: _pct(outcome.price1h), color: _pctColor(outcome.price1h)),
                _PricePoint(label: '1d', pct: _pct(outcome.price1d), color: _pctColor(outcome.price1d)),
                _PricePoint(label: '5d', pct: _pct(outcome.price5d), color: _pctColor(outcome.price5d)),
                _PricePoint(
                    label: 'Max +',
                    pct: outcome.maxGain1d != null ? '+${outcome.maxGain1d!.toStringAsFixed(2)}%' : '—',
                    color: Colors.green),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PricePoint extends StatelessWidget {
  final String label;
  final String pct;
  final Color color;
  const _PricePoint({required this.label, required this.pct, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
        const SizedBox(height: 2),
        Text(pct, style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }
}

// ── Dialogs ───────────────────────────────────────────────────────────────────

class _TookTradeDialog extends StatefulWidget {
  final String ticker;
  final double suggestedAmount;
  final double priceAtAlert;
  const _TookTradeDialog({
    required this.ticker,
    required this.suggestedAmount,
    required this.priceAtAlert,
  });

  @override
  State<_TookTradeDialog> createState() => _TookTradeDialogState();
}

class _TookTradeDialogState extends State<_TookTradeDialog> {
  final _entryCtrl = TextEditingController();
  final _amountCtrl = TextEditingController();
  final _notesCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _entryCtrl.text = widget.priceAtAlert.toStringAsFixed(4);
    _amountCtrl.text = widget.suggestedAmount.toStringAsFixed(2);
  }

  @override
  void dispose() {
    _entryCtrl.dispose();
    _amountCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('I took this trade — ${widget.ticker}'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _entryCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Entry price (£)', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _amountCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Amount invested (£)', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _notesCtrl,
              decoration: const InputDecoration(labelText: 'Notes (optional)', border: OutlineInputBorder()),
              maxLines: 2,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        ElevatedButton(
          onPressed: () {
            Navigator.pop(context, {
              'entry_price': double.tryParse(_entryCtrl.text),
              'amount': double.tryParse(_amountCtrl.text),
              'notes': _notesCtrl.text.isEmpty ? null : _notesCtrl.text,
            });
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}

class _CloseTradeDialog extends StatefulWidget {
  final String ticker;
  final double? entryPrice;
  const _CloseTradeDialog({required this.ticker, this.entryPrice});

  @override
  State<_CloseTradeDialog> createState() => _CloseTradeDialogState();
}

class _CloseTradeDialogState extends State<_CloseTradeDialog> {
  final _exitCtrl = TextEditingController();
  final _pnlCtrl = TextEditingController();
  final _notesCtrl = TextEditingController();

  @override
  void dispose() {
    _exitCtrl.dispose();
    _pnlCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Close trade — ${widget.ticker}'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _exitCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Exit price (£)', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pnlCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
              decoration: const InputDecoration(
                  labelText: 'Realised P&L (£, optional — auto-calculated if blank)',
                  border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _notesCtrl,
              decoration: const InputDecoration(labelText: 'Notes (optional)', border: OutlineInputBorder()),
              maxLines: 2,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        ElevatedButton(
          style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
          onPressed: () {
            final exitPrice = double.tryParse(_exitCtrl.text);
            if (exitPrice == null) return;
            Navigator.pop(context, {
              'manual_exit_price': exitPrice,
              'realised_pnl': double.tryParse(_pnlCtrl.text),
              'trade_notes': _notesCtrl.text.isEmpty ? null : _notesCtrl.text,
            });
          },
          child: const Text('Close Trade'),
        ),
      ],
    );
  }
}

// ── New helper widgets ────────────────────────────────────────────────────────

class _InfoCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String body;
  const _InfoCard({required this.icon, required this.color, required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: color,
                          fontSize: 13)),
                  const SizedBox(height: 4),
                  Text(body, style: const TextStyle(fontSize: 14, height: 1.4)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatPill extends StatelessWidget {
  final String label;
  final String value;
  const _StatPill({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.grey[100],
        borderRadius: BorderRadius.circular(20),
      ),
      child: RichText(
        text: TextSpan(
          style: DefaultTextStyle.of(context).style,
          children: [
            TextSpan(text: '$label  ', style: const TextStyle(color: Colors.grey, fontSize: 12)),
            TextSpan(text: value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
          ],
        ),
      ),
    );
  }
}

class _StepsCard extends StatelessWidget {
  final String ticker;
  final double amount;
  const _StepsCard({required this.ticker, required this.amount});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.green[50],
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.checklist, color: Colors.green, size: 18),
                SizedBox(width: 6),
                Text('How to act on this',
                    style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Colors.green,
                        fontSize: 13)),
              ],
            ),
            const SizedBox(height: 10),
            _Step('1', 'Tap the green button below to open Trading 212'),
            _Step('2', 'Search for "$ticker" in Trading 212'),
            _Step('3', 'Look at the chart — does the price look reasonable to you?'),
            _Step('4', 'If yes, tap Buy and enter up to £${amount.toStringAsFixed(0)}'),
            _Step('5', 'Come back here and tap "I took this trade" so we can track it'),
          ],
        ),
      ),
    );
  }
}

class _SellStepsCard extends StatelessWidget {
  final String ticker;
  const _SellStepsCard({required this.ticker});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.red[50],
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.checklist, color: Colors.red, size: 18),
                SizedBox(width: 6),
                Text('How to act on this',
                    style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Colors.red,
                        fontSize: 13)),
              ],
            ),
            const SizedBox(height: 10),
            _SellStep('1', 'Tap the red button below to open Trading 212'),
            _SellStep('2', 'Find your "$ticker" position in your portfolio'),
            _SellStep('3', 'Review your current profit or loss'),
            _SellStep('4', 'If you agree with the signal, tap Sell'),
            _SellStep('5', 'Come back here and tap "Close trade" to record your result'),
          ],
        ),
      ),
    );
  }
}

class _SellStep extends StatelessWidget {
  final String number;
  final String text;
  const _SellStep(this.number, this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 20,
            height: 20,
            alignment: Alignment.center,
            decoration: const BoxDecoration(
              color: Colors.red,
              shape: BoxShape.circle,
            ),
            child: Text(number,
                style: const TextStyle(
                    color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}

class _Step extends StatelessWidget {
  final String number;
  final String text;
  const _Step(this.number, this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 20,
            height: 20,
            alignment: Alignment.center,
            decoration: const BoxDecoration(
              color: Colors.green,
              shape: BoxShape.circle,
            ),
            child: Text(number,
                style: const TextStyle(
                    color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}

class _AdvancedRow extends StatelessWidget {
  final String label;
  final String value;
  const _AdvancedRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          SizedBox(
            width: 140,
            child: Text(label,
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ),
          Text(value,
              style: const TextStyle(
                  fontSize: 12, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}

// ── Shared widgets ────────────────────────────────────────────────────────────

class _ActionBadge extends StatelessWidget {
  final String action;
  const _ActionBadge({required this.action});

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color fg;
    switch (action) {
      case 'BUY_REVIEW':
        bg = Colors.green[100]!;
        fg = Colors.green[800]!;
      case 'REVIEW_SELL':
        bg = Colors.red[100]!;
        fg = Colors.red[800]!;
      case 'WATCH':
        bg = Colors.orange[100]!;
        fg = Colors.orange[800]!;
      case 'DO_NOT_ACT':
        bg = Colors.grey[300]!;
        fg = Colors.grey[800]!;
      default:
        bg = Colors.grey[200]!;
        fg = Colors.grey[700]!;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Text(action,
          style: TextStyle(fontWeight: FontWeight.bold, color: fg, fontSize: 16)),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;
  const _Stat({required this.label, required this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 11)),
        Text(value,
            style: TextStyle(
                fontSize: 18, fontWeight: FontWeight.bold, color: valueColor)),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final String body;
  const _Section({required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontWeight: FontWeight.bold, color: Colors.grey)),
            const SizedBox(height: 4),
            Text(body),
          ],
        ),
      ),
    );
  }
}

class _BulletSection extends StatelessWidget {
  final String title;
  final List<String> items;
  final Color color;
  const _BulletSection(
      {required this.title, required this.items, required this.color});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontWeight: FontWeight.bold, color: Colors.grey)),
            const SizedBox(height: 8),
            ...items.map(
              (item) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.circle, size: 8, color: color),
                    const SizedBox(width: 8),
                    Expanded(child: Text(item, style: const TextStyle(fontSize: 13))),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
