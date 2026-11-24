import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/analysis_result.dart';

/// Lightweight coach-facing sprint profile built without a custom canvas.
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
    final current = _validPoints(analysis.currentCurve);
    final baseline = _validPoints(analysis.baselineCurve);
    final available = current.length >= 2;

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
            if (analysis.quality.status == 'limited') ...[
              const SizedBox(height: 8),
              const Align(
                alignment: Alignment.centerLeft,
                child: Chip(label: Text('Limited evidence')),
              ),
            ],
            const SizedBox(height: 14),
            if (available) ...[
              RepaintBoundary(
                child: _ForceVelocityPlot(current: current, baseline: baseline),
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _Legend(
                    color: Theme.of(context).colorScheme.primary,
                    label: 'This match',
                  ),
                  const SizedBox(width: 18),
                  _Legend(
                    color: Theme.of(context).colorScheme.outline,
                    label: baseline.length >= 2
                        ? 'Personal baseline'
                        : 'Baseline forming',
                    dashed: true,
                  ),
                ],
              ),
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
                child: Text(_summary(analysis)),
              ),
            ] else
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  analysis.events.isEmpty
                      ? 'No valid sprint acceleration was identified in this video.'
                      : '${analysis.events.length} sprint acceleration${analysis.events.length == 1 ? '' : 's'} found. A curve needs at least two usable speed points.',
                ),
              ),
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

  static List<ForceVelocityCurvePoint> _validPoints(
    List<ForceVelocityCurvePoint> source,
  ) {
    final points =
        source
            .where(
              (point) =>
                  point.velocityMps.isFinite &&
                  point.forceNPerKg.isFinite &&
                  point.velocityMps >= 0 &&
                  point.forceNPerKg >= 0,
            )
            .toList(growable: false)
          ..sort((a, b) => a.velocityMps.compareTo(b.velocityMps));
    return points.length <= 40
        ? points
        : points.take(40).toList(growable: false);
  }

  static String _summary(ForceVelocityAnalysis analysis) {
    final supplied = analysis.comparisonSummary?.trim();
    if (supplied != null && supplied.isNotEmpty && supplied.length <= 220) {
      return supplied;
    }
    return '${analysis.events.length} valid sprint acceleration${analysis.events.length == 1 ? '' : 's'} identified in this match.';
  }
}

class _ForceVelocityPlot extends StatelessWidget {
  const _ForceVelocityPlot({required this.current, required this.baseline});

  final List<ForceVelocityCurvePoint> current;
  final List<ForceVelocityCurvePoint> baseline;

  @override
  Widget build(BuildContext context) {
    final all = <ForceVelocityCurvePoint>[...current, ...baseline];
    final xMin = all.map((point) => point.velocityMps).reduce(math.min);
    final rawXMax = all.map((point) => point.velocityMps).reduce(math.max);
    final xMax = rawXMax > xMin ? rawXMax : xMin + 1;
    final yMax = math.max(
      1.0,
      all.map((point) => point.forceNPerKg).reduce(math.max) * 1.15,
    );
    final colors = Theme.of(context).colorScheme;

    return SizedBox(
      key: const Key('force-velocity-chart'),
      height: 220,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Force (N/kg)', style: Theme.of(context).textTheme.labelSmall),
          const SizedBox(height: 4),
          Expanded(
            child: Row(
              children: [
                SizedBox(
                  width: 34,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(yMax.toStringAsFixed(1)),
                      Text((yMax / 2).toStringAsFixed(1)),
                      const Text('0'),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      Offset position(ForceVelocityCurvePoint point) => Offset(
                        (point.velocityMps - xMin) /
                            (xMax - xMin) *
                            constraints.maxWidth,
                        constraints.maxHeight -
                            point.forceNPerKg / yMax * constraints.maxHeight,
                      );
                      final currentOffsets = current.map(position).toList();
                      final baselineOffsets = baseline.map(position).toList();
                      return ClipRect(
                        child: Stack(
                          children: [
                            for (final fraction in const [0.0, .5, 1.0])
                              Positioned(
                                left: 0,
                                right: 0,
                                top: constraints.maxHeight * fraction,
                                child: Container(
                                  height: 1,
                                  color: colors.outlineVariant,
                                ),
                              ),
                            ..._lineWidgets(
                              baselineOffsets,
                              colors.outline,
                              dashed: true,
                            ),
                            ..._lineWidgets(currentOffsets, colors.primary),
                            for (final point in currentOffsets)
                              Positioned(
                                left: point.dx - 3,
                                top: point.dy - 3,
                                child: Container(
                                  width: 6,
                                  height: 6,
                                  decoration: BoxDecoration(
                                    color: colors.primary,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(left: 40, top: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(xMin.toStringAsFixed(1)),
                Text(
                  'Speed (m/s)',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
                Text(xMax.toStringAsFixed(1)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static List<Widget> _lineWidgets(
    List<Offset> points,
    Color color, {
    bool dashed = false,
  }) {
    final widgets = <Widget>[];
    for (var index = 1; index < points.length; index++) {
      final start = points[index - 1];
      final end = points[index];
      final delta = end - start;
      final length = delta.distance;
      if (!length.isFinite || length <= 0) continue;
      final pieces = dashed ? math.max(1, (length / 12).floor()) : 1;
      for (var piece = 0; piece < pieces; piece++) {
        if (dashed && piece.isOdd) continue;
        final from = Offset.lerp(start, end, piece / pieces)!;
        final to = Offset.lerp(start, end, (piece + 1) / pieces)!;
        final segment = to - from;
        widgets.add(
          Positioned(
            left: from.dx,
            top: from.dy - 1.25,
            child: Transform.rotate(
              alignment: Alignment.centerLeft,
              angle: math.atan2(segment.dy, segment.dx),
              child: Container(
                width: segment.distance,
                height: 2.5,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
          ),
        );
      }
    }
    return widgets;
  }
}

class _Legend extends StatelessWidget {
  const _Legend({
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
        child: Row(
          children: [
            Expanded(child: Container(height: 2.5, color: color)),
            if (dashed) ...[
              const SizedBox(width: 4),
              Expanded(child: Container(height: 2.5, color: color)),
            ],
          ],
        ),
      ),
      const SizedBox(width: 6),
      Text(label, style: Theme.of(context).textTheme.bodySmall),
    ],
  );
}
