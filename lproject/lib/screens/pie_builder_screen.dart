import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../models/pie_model.dart';
import '../services/device_service.dart';
import 'pie_result_screen.dart';

const _goals = [
  ('safer_core', 'Safer Core', 'Low-risk, ETF-heavy capital preservation'),
  ('balanced_growth', 'Balanced Growth', 'Mix of growth and stability'),
  ('ai_technology', 'AI & Technology', 'High-growth tech exposure'),
  ('clean_energy', 'Clean Energy', 'Renewables and ESG'),
  ('dividend_income', 'Dividend Income', 'Regular income from dividends'),
  ('custom', 'Custom', 'Choose your own themes'),
];

const _themes = [
  ('global_equity', 'Global Equity'),
  ('sp500', 'S&P 500'),
  ('technology', 'Technology'),
  ('semiconductors', 'Semiconductors'),
  ('healthcare', 'Healthcare'),
  ('dividend_income', 'Dividend Income'),
  ('clean_energy', 'Clean Energy'),
  ('uk_large_cap', 'UK Large Cap'),
  ('defensive', 'Defensive'),
];

const _horizons = ['6 months', '1 year', '3 years', '5 years', '10+ years'];

class PieBuilderScreen extends StatefulWidget {
  const PieBuilderScreen({super.key});

  @override
  State<PieBuilderScreen> createState() => _PieBuilderScreenState();
}

class _PieBuilderScreenState extends State<PieBuilderScreen> {
  final _amountController = TextEditingController(text: '500');
  String _selectedGoal = 'balanced_growth';
  String _riskLevel = 'medium';
  String _timeHorizon = '3 years';
  final Set<String> _preferredThemes = {};
  final Set<String> _excludedThemes = {};
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _buildPie() async {
    final amountText = _amountController.text.trim();
    final amount = double.tryParse(amountText);
    if (amount == null || amount <= 0) {
      setState(() => _error = 'Please enter a valid amount.');
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final res = await http.post(
        Uri.parse('${ApiConfig.baseUrl}/pie/build'),
        headers: {
          'Content-Type': 'application/json',
          'device-id': DeviceService.instance.deviceId,
        },
        body: jsonEncode({
          'goal': _selectedGoal,
          'risk_level': _riskLevel,
          'total_amount': amount,
          'time_horizon': _timeHorizon,
          'preferred_themes': _preferredThemes.toList(),
          'excluded_themes': _excludedThemes.toList(),
        }),
      );

      if (!mounted) return;

      if (res.statusCode == 200) {
        final pie = PieBuildResult.fromJson(
            jsonDecode(res.body) as Map<String, dynamic>);
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => PieResultScreen(pie: pie)),
        );
      } else if (res.statusCode == 429) {
        _showUpgradeModal();
      } else {
        final detail =
            (jsonDecode(res.body) as Map<String, dynamic>)['detail'] as String?
                ?? 'Build failed. Try different themes or a larger amount.';
        setState(() => _error = detail);
      }
    } catch (_) {
      setState(() => _error = 'Connection failed. Ensure backend is running.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showUpgradeModal() {
    showModalBottomSheet(
      context: context,
      builder: (_) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.pie_chart, size: 48, color: Colors.orange),
            const SizedBox(height: 12),
            const Text('Daily Pie Limit Reached',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Free users can build 1 Pie per day.\nUpgrade to Pro for more builds, saved history, and Pie monitoring.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Upgrade to Pro — £9.99/mo'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pie Builder')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Goal
          const _SectionLabel('Investment Goal'),
          DropdownButtonFormField<String>(
            initialValue: _selectedGoal,
            decoration: const InputDecoration(border: OutlineInputBorder()),
            items: _goals
                .map((g) => DropdownMenuItem(
                      value: g.$1,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(g.$2,
                              style:
                                  const TextStyle(fontWeight: FontWeight.bold)),
                          Text(g.$3,
                              style: const TextStyle(
                                  fontSize: 12, color: Colors.grey)),
                        ],
                      ),
                    ))
                .toList(),
            onChanged: (v) => setState(() => _selectedGoal = v!),
          ),

          const SizedBox(height: 16),

          // Risk level
          const _SectionLabel('Risk Level'),
          _RiskSelector(
            selected: _riskLevel,
            onChanged: (v) => setState(() => _riskLevel = v),
          ),

          const SizedBox(height: 16),

          // Amount
          const _SectionLabel('Total Amount (£)'),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              prefixText: '£ ',
              border: OutlineInputBorder(),
              hintText: '500',
            ),
          ),

          const SizedBox(height: 16),

          // Time horizon
          const _SectionLabel('Time Horizon'),
          DropdownButtonFormField<String>(
            initialValue: _timeHorizon,
            decoration: const InputDecoration(border: OutlineInputBorder()),
            items: _horizons
                .map((h) => DropdownMenuItem(value: h, child: Text(h)))
                .toList(),
            onChanged: (v) => setState(() => _timeHorizon = v!),
          ),

          const SizedBox(height: 16),

          // Theme preferences (only shown for custom goal)
          if (_selectedGoal == 'custom') ...[
            const _SectionLabel('Preferred Themes'),
            _ThemeChips(
              themes: _themes,
              selected: _preferredThemes,
              color: Colors.blue,
              onToggle: (t) => setState(() {
                _preferredThemes.contains(t)
                    ? _preferredThemes.remove(t)
                    : _preferredThemes.add(t);
                _excludedThemes.remove(t);
              }),
            ),
            const SizedBox(height: 12),
            const _SectionLabel('Excluded Themes'),
            _ThemeChips(
              themes: _themes,
              selected: _excludedThemes,
              color: Colors.red,
              onToggle: (t) => setState(() {
                _excludedThemes.contains(t)
                    ? _excludedThemes.remove(t)
                    : _excludedThemes.add(t);
                _preferredThemes.remove(t);
              }),
            ),
            const SizedBox(height: 8),
          ],

          if (_error != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.orange[50],
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange[300]!),
              ),
              child: Text(_error!, style: const TextStyle(color: Colors.orange)),
            ),
          ],

          const SizedBox(height: 20),

          ElevatedButton.icon(
            onPressed: _isLoading ? null : _buildPie,
            icon: _isLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.auto_graph),
            label: Text(
              _isLoading ? 'Building…' : 'Build My Pie',
              style: const TextStyle(fontSize: 16),
            ),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.all(16),
              backgroundColor: Colors.blue,
              foregroundColor: Colors.white,
            ),
          ),

          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
      );
}

class _RiskSelector extends StatelessWidget {
  final String selected;
  final ValueChanged<String> onChanged;
  const _RiskSelector({required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    const levels = [
      ('low', 'Low', Colors.green),
      ('medium', 'Medium', Colors.orange),
      ('high', 'High', Colors.red),
    ];
    return Row(
      children: levels.map((l) {
        final isSelected = selected == l.$1;
        return Expanded(
          child: GestureDetector(
            onTap: () => onChanged(l.$1),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 4),
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: isSelected ? l.$3.withValues(alpha: 0.15) : Colors.grey[100],
                border: Border.all(
                    color: isSelected ? l.$3 : Colors.grey[300]!, width: 2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                children: [
                  Text(l.$2,
                      style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: isSelected ? l.$3 : Colors.grey)),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _ThemeChips extends StatelessWidget {
  final List<(String, String)> themes;
  final Set<String> selected;
  final Color color;
  final ValueChanged<String> onToggle;

  const _ThemeChips({
    required this.themes,
    required this.selected,
    required this.color,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 4,
      children: themes.map((t) {
        final isSelected = selected.contains(t.$1);
        return FilterChip(
          label: Text(t.$2),
          selected: isSelected,
          selectedColor: color.withValues(alpha: 0.2),
          checkmarkColor: color,
          onSelected: (_) => onToggle(t.$1),
        );
      }).toList(),
    );
  }
}
