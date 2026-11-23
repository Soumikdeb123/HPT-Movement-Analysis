import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/analysis_result.dart';

class ForceVelocityChart extends StatelessWidget {
  const ForceVelocityChart({
    super.key,
    required this.analysis,
    this.onViewEvents,
  });

  final ForceVelocityAnalysis analysis;
  final VoidCallback? onViewEvents;

  @override
  Widget build(BuildContext context) {
    final available = analysis.currentCurve.length >= 2;
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Match Sprint Force–Velocity',
              style: Theme.of(context).textTheme.titleLarge
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            const Text(
              'This match compared with the player’s personal sprint baseline.',
            ),
            if (analysis.quality.status == 'limited') ...[
              const SizedBox(height: 10),
              const Align(
                alignment: Alignment.centerLeft,
                child: Chip(label: Text('Limited evidence')),
              ),
            ],
            const SizedBox(height: 16),
            if (!available)
              _Unavailable(analysis: analysis)
            else ...[
              AspectRatio(
                key: const Key('force-velocity-chart'),
                aspectRatio: 1.45,
                child: CustomPaint(
                  painter: _ForceVelocityPainter(
                    current: analysis.currentCurve,
                    baseline: analysis.baselineCurve,
                    currentColor: Theme.of(context).colorScheme.primary,
                    baselineColor: Theme.of(context).colorScheme.outline,
                    gridColor: Theme.of(context).colorScheme.outlineVariant,
                    textColor: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
              const SizedBox(height: 10),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _LegendLine(
                    color: Theme.of(context).colorScheme.primary,
                    label: 'This match',
                  ),
                  const SizedBox(width: 20),
                  _LegendLine(
                    color: Theme.of(context).colorScheme.outline,
                    label: analysis.baselineCurve.isEmpty
                        ? 'Personal baseline forming'
                        : 'Personal baseline',
                    dashed: true,
                  ),
                ],
              ),
            ],
            if (available) ...[
              const SizedBox(height: 16),
              Text(
                'What this video shows',
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer
                      .withValues(alpha: .45),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  analysis.comparisonSummary ??
                      'This match identified ${analysis.events.length} valid sprint accelerations.',
                ),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton.icon(
              key: const Key('view-all-sprint-events-button'),
              onPressed: analysis.events.isEmpty ? null : onViewEvents,
              icon: const Icon(Icons.play_circle_outline),
              label: Text('View all ${analysis.events.length} sprint events'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable({required this.analysis});
  final ForceVelocityAnalysis analysis;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.errorContainer,
      borderRadius: BorderRadius.circular(14),
    ),
    child: Text(
      analysis.events.isEmpty
          ? 'No valid sprint acceleration was identified in this video.'
          : '${analysis.events.length} valid sprint acceleration${analysis.events.length == 1 ? '' : 's'} found. '
                'More evidence is needed to draw a reliable curve.',
      style: const TextStyle(fontWeight: FontWeight.w600),
    ),
  );
}

class _LegendLine extends StatelessWidget {
  const _LegendLine({
    required this.color,
    required this.label,
    this.dashed = false,
  });
  final Color color;
  final String label;
  final bool dashed;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      SizedBox(
        width: 24,
        height: 8,
        child: CustomPaint(painter: _LegendPainter(color, dashed)),
      ),
      const SizedBox(width: 6),
      Text(label, style: Theme.of(context).textTheme.bodySmall),
    ],
  );
}

class _LegendPainter extends CustomPainter {
  const _LegendPainter(this.color, this.dashed);
  final Color color;
  final bool dashed;
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    if (!dashed) {
      canvas.drawLine(
        Offset(0, size.height / 2),
        Offset(size.width, size.height / 2),
        paint,
      );
      return;
    }
    for (double x = 0; x < size.width; x += 7) {
      canvas.drawLine(
        Offset(x, size.height / 2),
        Offset(math.min(x + 4, size.width), size.height / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _LegendPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.dashed != dashed;
}

class _ForceVelocityPainter extends CustomPainter {
  const _ForceVelocityPainter({
    required this.current,
    required this.baseline,
    required this.currentColor,
    required this.baselineColor,
    required this.gridColor,
    required this.textColor,
  });

  final List<ForceVelocityCurvePoint> current;
  final List<ForceVelocityCurvePoint> baseline;
  final Color currentColor;
  final Color baselineColor;
  final Color gridColor;
  final Color textColor;

  @override
  void paint(Canvas canvas, Size size) {
    const left = 48.0, top = 14.0, right = 12.0, bottom = 42.0;
    final plot = Rect.fromLTRB(
      left,
      top,
      size.width - right,
      size.height - bottom,
    );
    if (plot.width <= 0 || plot.height <= 0 || current.length < 2) return;

    final xMin = baseline.isEmpty
        ? current.first.velocityMps
        : baseline.first.velocityMps;
    final xMax = baseline.isEmpty
        ? current.last.velocityMps
        : baseline.last.velocityMps;
    if (xMax <= xMin) return;
    final visibleCurrent = current
        .where(
          (point) =>
              point.velocityMps >= xMin - .001 &&
              point.velocityMps <= xMax + .001,
        )
        .toList();
    final allVisible = <ForceVelocityCurvePoint>[
      ...visibleCurrent,
      ...baseline,
    ];
    if (allVisible.isEmpty) return;
    final yMax = math.max(
      1.0,
      allVisible.map((point) => point.forceNPerKg).reduce(math.max) * 1.18,
    );
    final grid = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    for (var index = 0; index <= 4; index++) {
      final y = plot.bottom - plot.height * index / 4;
      canvas.drawLine(Offset(plot.left, y), Offset(plot.right, y), grid);
      _label(canvas, (yMax * index / 4).toStringAsFixed(1), Offset(4, y - 7));
    }
    canvas.drawLine(plot.bottomLeft, plot.topLeft, grid);
    canvas.drawLine(plot.bottomLeft, plot.bottomRight, grid);
    _label(canvas, 'N/kg', const Offset(4, 0));
    _label(
      canvas,
      xMin.toStringAsFixed(1),
      Offset(plot.left - 7, plot.bottom + 9),
    );
    _label(
      canvas,
      xMax.toStringAsFixed(1),
      Offset(plot.right - 15, plot.bottom + 9),
    );
    _label(
      canvas,
      'Speed (m/s)',
      Offset(plot.center.dx - 32, plot.bottom + 25),
    );

    Offset point(ForceVelocityCurvePoint value) => Offset(
      plot.left + (value.velocityMps - xMin) / (xMax - xMin) * plot.width,
      plot.bottom - value.forceNPerKg / yMax * plot.height,
    );
    _drawSolid(canvas, visibleCurrent.map(point).toList(), currentColor);
    if (baseline.length >= 2) {
      _drawDashed(canvas, baseline.map(point).toList(), baselineColor);
    }
  }

  void _drawSolid(Canvas canvas, List<Offset> points, Color color) {
    if (points.length < 2) return;
    canvas.drawPath(
      Path()..addPolygon(points, false),
      Paint()
        ..color = color
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke,
    );
  }

  void _drawDashed(Canvas canvas, List<Offset> points, Color color) {
    if (points.length < 2) return;
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    for (var index = 1; index < points.length; index++) {
      if (index.isOdd) canvas.drawLine(points[index - 1], points[index], paint);
    }
  }

  void _label(Canvas canvas, String text, Offset offset) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(fontSize: 10, color: textColor),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, offset);
  }

  @override
  bool shouldRepaint(covariant _ForceVelocityPainter oldDelegate) =>
      oldDelegate.current != current ||
      oldDelegate.baseline != baseline ||
      oldDelegate.currentColor != currentColor;
}
