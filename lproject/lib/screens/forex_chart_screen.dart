import 'dart:convert';
import 'package:candlesticks/candlesticks.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';

class ForexChartScreen extends StatefulWidget {
  final String pair;
  const ForexChartScreen({super.key, required this.pair});

  @override
  State<ForexChartScreen> createState() => _ForexChartScreenState();
}

class _ForexChartScreenState extends State<ForexChartScreen> {
  List<Candle> _candles = [];
  bool _loading = true;
  String? _error;
  String _interval = '1h';

  static const _intervals = ['1h', '4h', '1d'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final res = await http.get(
        Uri.parse(ApiConfig.forexChart(widget.pair, _interval)),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (res.statusCode == 200) {
        final json = jsonDecode(res.body) as Map<String, dynamic>;
        final bars = (json['bars'] as List).cast<Map<String, dynamic>>();
        final candles = bars.map((b) => Candle(
          date: DateTime.parse(b['t'] as String),
          open: (b['o'] as num).toDouble(),
          high: (b['h'] as num).toDouble(),
          low: (b['l'] as num).toDouble(),
          close: (b['c'] as num).toDouble(),
          volume: (b['v'] as num).toDouble(),
        )).toList();
        // candlesticks package expects newest-first
        setState(() => _candles = candles.reversed.toList());
      } else {
        setState(() => _error = 'No chart data (${res.statusCode})');
      }
    } catch (_) {
      setState(() => _error = 'Backend unavailable.');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          widget.pair,
          style: GoogleFonts.orbitron(fontWeight: FontWeight.w700, fontSize: 15),
        ),
        actions: [
          ..._intervals.map((iv) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 3),
            child: ChoiceChip(
              label: Text(iv, style: GoogleFonts.dmSans(fontSize: 12)),
              selected: _interval == iv,
              selectedColor: AppColors.cyan,
              onSelected: (_) {
                if (_interval != iv) {
                  setState(() => _interval = iv);
                  _load();
                }
              },
            ),
          )),
          const SizedBox(width: 8),
          IconButton(icon: const Icon(Icons.refresh, size: 20), onPressed: _load),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: AppColors.cyan));
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppColors.pink, size: 44),
            const SizedBox(height: 12),
            Text(_error!, style: GoogleFonts.dmSans(color: AppColors.textMuted)),
          ],
        ),
      );
    }
    if (_candles.isEmpty) {
      return Center(
        child: Text('No candles', style: GoogleFonts.dmSans(color: AppColors.textMuted)),
      );
    }
    return Candlesticks(candles: _candles);
  }
}
