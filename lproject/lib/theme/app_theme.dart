import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// ── Brand colours ────────────────────────────────────────────────────────────
class AppColors {
  AppColors._();

  static const background = Color(0xFF080818);
  static const surface = Color(0xFF0E0E2A);
  static const surfaceHigh = Color(0xFF14143A);
  static const border = Color(0x12FFFFFF);
  static const borderAccent = Color(0x33FF8C00);

  static const orange = Color(0xFFFF8C00);
  static const cyan = Color(0xFF00E5FF);
  static const green = Color(0xFF39FF6E);
  static const pink = Color(0xFFFF3CA0);
  static const purple = Color(0xFF7B2FBE);

  static const textPrimary = Color(0xFFF0F0FF);
  static const textMuted = Color(0xFF8888AA);

  // Semantic
  static const buy = green;
  static const sell = pink;
  static const watch = orange;
  static const inactive = Color(0xFF444466);
}

// ── Theme ─────────────────────────────────────────────────────────────────────
ThemeData buildAppTheme() {
  final base = ThemeData.dark(useMaterial3: true);

  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.orange,
      secondary: AppColors.cyan,
      surface: AppColors.surface,
      onSurface: AppColors.textPrimary,
      onPrimary: Colors.black,
    ),
    textTheme: GoogleFonts.dmSansTextTheme(base.textTheme).copyWith(
      displayLarge: GoogleFonts.orbitron(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w700,
      ),
      displayMedium: GoogleFonts.orbitron(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w700,
      ),
      headlineLarge: GoogleFonts.orbitron(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w700,
      ),
      headlineMedium: GoogleFonts.orbitron(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w600,
      ),
      headlineSmall: GoogleFonts.orbitron(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w600,
      ),
      titleLarge: GoogleFonts.orbitron(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w600,
        fontSize: 16,
      ),
      titleMedium: GoogleFonts.dmSans(
        color: AppColors.textPrimary,
        fontWeight: FontWeight.w500,
      ),
      bodyLarge: GoogleFonts.dmSans(color: AppColors.textPrimary),
      bodyMedium: GoogleFonts.dmSans(color: AppColors.textMuted),
      labelSmall: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 11),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.surface,
      foregroundColor: AppColors.textPrimary,
      elevation: 0,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: GoogleFonts.orbitron(
        color: AppColors.orange,
        fontWeight: FontWeight.w700,
        fontSize: 16,
      ),
      iconTheme: const IconThemeData(color: AppColors.textMuted),
      actionsIconTheme: const IconThemeData(color: AppColors.textMuted),
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: const BorderSide(color: AppColors.border),
      ),
      margin: EdgeInsets.zero,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.orange,
        foregroundColor: Colors.black,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        textStyle: GoogleFonts.dmSans(fontWeight: FontWeight.w600, fontSize: 15),
        shadowColor: AppColors.orange.withValues(alpha: 0.4),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.cyan,
        side: const BorderSide(color: AppColors.cyan),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        textStyle: GoogleFonts.dmSans(fontWeight: FontWeight.w500),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surfaceHigh,
      hintStyle: GoogleFonts.dmSans(color: AppColors.textMuted),
      labelStyle: GoogleFonts.dmSans(color: AppColors.textMuted),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: AppColors.orange, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: AppColors.pink),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: AppColors.pink, width: 1.5),
      ),
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: AppColors.orange,
      foregroundColor: Colors.black,
      elevation: 4,
    ),
    dividerTheme: const DividerThemeData(color: AppColors.border, thickness: 1),
    iconTheme: const IconThemeData(color: AppColors.textMuted),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.orange,
    ),
    chipTheme: ChipThemeData(
      backgroundColor: AppColors.surfaceHigh,
      labelStyle: GoogleFonts.dmSans(color: AppColors.textPrimary, fontSize: 12),
      side: const BorderSide(color: AppColors.border),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
    ),
  );
}
