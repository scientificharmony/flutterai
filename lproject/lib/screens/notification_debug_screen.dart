import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_theme.dart';

class NotificationDebugScreen extends StatelessWidget {
  final Map<String, dynamic> data;
  const NotificationDebugScreen({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    final pretty = const JsonEncoder.withIndent('  ').convert(data);
    return Scaffold(
      appBar: AppBar(
        title: Text('NOTIFICATION DEBUG',
            style: GoogleFonts.orbitron(
                color: AppColors.cyan, fontWeight: FontWeight.w700, fontSize: 15)),
      ),
      body: Padding(
        padding: const EdgeInsets.all(14),
        child: SelectableText(
          pretty,
          style: GoogleFonts.dmSans(color: AppColors.textPrimary),
        ),
      ),
    );
  }
}

