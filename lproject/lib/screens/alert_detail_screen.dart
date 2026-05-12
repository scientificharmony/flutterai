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

class _AlertDetail extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final expired = alert.isExpired;
    final canExecute = alert.trading212ReviewEnabled &&
        alert.actionStrength >= 70 &&
        (alert.action == 'BUY_REVIEW' || alert.action == 'REVIEW_SELL') &&
        !expired;
    final confidenceColor = alert.confidence >= 70 ? Colors.green : Colors.orange;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(alert.ticker,
                          style: const TextStyle(
                              fontSize: 32, fontWeight: FontWeight.bold)),
                      _ActionBadge(action: alert.action),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _Stat(label: "Suggested", value: "£${alert.suggestedAmount.toStringAsFixed(2)}"),
                      _Stat(label: "Price at Alert", value: "£${alert.priceAtAlert.toStringAsFixed(4)}"),
                      _Stat(label: "Formula Score", value: "${alert.formulaScore}/100"),
                      _Stat(
                          label: "Claude Confidence",
                          value: "${alert.claudeConfidence}/100",
                          valueColor: confidenceColor),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _Stat(
                          label: "Action Strength",
                          value: "${alert.actionStrength}/100"),
                      _Stat(label: "Action Label", value: alert.actionLabel),
                      _Stat(
                          label: "Expires",
                          value: expired
                              ? "Expired"
                              : DateFormat('HH:mm').format(alert.expiresAt.toLocal()),
                          valueColor: expired ? Colors.red : null),
                    ],
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),

          // Rationale
          _Section(title: "Rationale", body: alert.rationale),
          const SizedBox(height: 8),
          _Section(title: "Risk Note", body: alert.riskNote),

          if (alert.keyFactors.isNotEmpty) ...[
            const SizedBox(height: 8),
            _BulletSection(title: "Key Factors", items: alert.keyFactors, color: Colors.blue),
          ],

          if (alert.blockingRisks.isNotEmpty) ...[
            const SizedBox(height: 8),
            _BulletSection(title: "Blocking Risks", items: alert.blockingRisks, color: Colors.red),
          ],

          // Safety flags
          if (alert.safetyFlags.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...alert.safetyFlags.map(
              (f) => Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.orange[50],
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange[300]!),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.warning_amber, color: Colors.orange, size: 16),
                    const SizedBox(width: 8),
                    Expanded(child: Text(f, style: const TextStyle(fontSize: 13))),
                  ],
                ),
              ),
            ),
          ],

          const SizedBox(height: 16),

          // Outcome card
          _OutcomeCard(
            outcome: outcome,
            onTookTrade: onTookTrade,
            onIgnored: onIgnored,
            onWatching: onWatching,
            onCloseTrade: onCloseTrade,
          ),

          const SizedBox(height: 16),

          // Price tracking (if available)
          if (outcome != null &&
              (outcome!.price1h != null || outcome!.price1d != null)) ...[
            _PriceTrackingCard(outcome: outcome!, priceAtAlert: alert.priceAtAlert),
            const SizedBox(height: 16),
          ],

          // Disclaimer
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.grey[100],
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.grey[300]!),
            ),
              child: const Text(
              'This app does not place trades. You are responsible for all trading decisions. Past performance is not indicative of future results.',
              style: TextStyle(fontSize: 11, color: Colors.grey),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: 8),
          Tooltip(
            message: 'Action Strength ranks how strongly this setup matches your rules. It is not a guarantee or probability of profit.',
            child: Text(
              alert.actionStrengthDisclaimer,
              style: TextStyle(fontSize: 11, color: Colors.grey[700]),
            ),
          ),

          const SizedBox(height: 16),

          OutlinedButton.icon(
            onPressed: onCopy,
            icon: const Icon(Icons.copy),
            label: const Text('Copy Order Details'),
          ),

          const SizedBox(height: 8),

          ElevatedButton.icon(
            onPressed: canExecute ? onOpenT212 : null,
            icon: const Icon(Icons.open_in_new),
            label: const Text('Review in Trading 212'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.green,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.all(16),
              disabledBackgroundColor: Colors.grey[300],
            ),
          ),

          if (!canExecute)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                expired
                    ? 'This alert has expired.'
                    : alert.action == 'WATCH'
                        ? 'Watch only — not strong enough to review yet.'
                        : alert.safetyFlags.any((f) => f.toLowerCase().contains('validation'))
                            ? 'Review disabled — Trading 212 validation failed.'
                            : 'Review disabled — safety checks did not pass.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey[600], fontSize: 12),
              ),
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
