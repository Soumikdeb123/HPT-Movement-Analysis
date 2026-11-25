import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/analysis_result.dart';

/// Coach-facing session-average movement Force–Velocity profile.
class ForceVelocityChart extends StatelessWidget {
  const ForceVelocityChart({
    super.key,
    required this.analysis,
    this.onViewEvents,
  });

  final ForceVelocityAnalysis analysis;
  final VoidCallback? onViewEvents;

  static const _matchColor = Color(0xFF006C4C);
  static const _baselineColor = Color(0xFFC44F00);

  @override
  Widget build(BuildContext context) {
    final current = _validPoints(analysis.currentCurve);
    final baseline = _validPoints(analysis.baselineCurve);
    final available = current.length >= 2;
    final hasBaselineComparison = const {
      'above',
      'below',
      'close',
    }.contains(analysis.comparisonStatus);

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Movement Force–Velocity',
              style: Theme.of(context).textTheme.titleLarge
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 14),
            if (available) ...[
              RepaintBoundary(
                child: _ForceVelocityPlot(current: current, baseline: baseline),
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _Legend(color: _matchColor, label: 'This match'),
                  if (baseline.length >= 2) ...[
                    const SizedBox(width: 18),
                    _Legend(
                      color: _baselineColor,
                      label: 'Personal baseline',
                      dashed: true,
                    ),
                  ],
                ],
              ),
              if (analysis.resolvedPeakEstimatedPropulsionN
                  case final peak?) ...[
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      analysis.massKg == null
                          ? 'Peak estimated propulsion'
                          : 'Peak estimated propulsion (${analysis.massKg!.toStringAsFixed(0)} kg)',
                    ),
                    Text(
                      '${peak.round()} N',
                      style: Theme.of(context).textTheme.titleMedium
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 16),
              Row(
                children: [
                  Text(
                    'Match performance',
                    style: Theme.of(context).textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  if (hasBaselineComparison)
                    IconButton(
                      key: const Key('force-velocity-info-button'),
                      tooltip: 'Possible explanations',
                      visualDensity: VisualDensity.compact,
                      onPressed: () => _showPossibleExplanations(context),
                      icon: const Icon(Icons.info_outline, size: 20),
                    ),
                ],
              ),
              Text(
                _headline(analysis),
                style: Theme.of(context).textTheme.titleSmall
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              if (_detail(analysis).isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(_detail(analysis)),
              ],
            ] else
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Text(
                  'Movement Force–Velocity is unavailable for this video.',
                ),
              ),
            const SizedBox(height: 16),
            FilledButton.icon(
              key: const Key('review-key-movements-button'),
              onPressed: analysis.events.isEmpty ? null : onViewEvents,
              icon: const Icon(Icons.play_circle_outline),
              label: const Text('Review key movement moments'),
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

  static String _headline(ForceVelocityAnalysis analysis) {
    final supplied = analysis.comparisonSummary?.trim();
    return supplied == null || supplied.isEmpty
        ? 'Personal baseline is being built (3 analyses required)'
        : supplied;
  }

  static String _detail(ForceVelocityAnalysis analysis) =>
      analysis.comparisonDetail?.trim() ?? '';

  void _showPossibleExplanations(BuildContext context) {
    const aboveExplanations = [
      'The first movement was quicker.',
      'Acceleration was maintained after the initial movement.',
      'Chasing and recovery movement was more assertive.',
      'Body position and push-off may have been more effective.',
      'Key movements were performed at a higher intensity.',
    ];
    const belowExplanations = [
      'Acceleration was not maintained after the initial movement.',
      'The player reached position more slowly than usual.',
      'Body position or footwork may have reduced propulsion.',
      'Movement performance may have dropped later in the session.',
      'The movement may have been tactical rather than full effort.',
    ];
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.82,
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Possible explanations',
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                const _ExplanationGroup(
                  title: 'When performance is above usual',
                  explanations: aboveExplanations,
                ),
                const SizedBox(height: 8),
                const _ExplanationGroup(
                  title: 'When performance is below usual',
                  explanations: belowExplanations,
                ),
              ],
            ),
          ),
        ),
      ),
    );
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
                              ForceVelocityChart._baselineColor,
                              dashed: true,
                              thickness: 3.2,
                            ),
                            ..._lineWidgets(
                              currentOffsets,
                              ForceVelocityChart._matchColor,
                              thickness: 3.6,
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
                Text(
                  xMin.toStringAsFixed(1),
                  key: const Key('force-velocity-x-min'),
                ),
                Text(
                  'Speed (m/s)',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
                Text(
                  xMax.toStringAsFixed(1),
                  key: const Key('force-velocity-x-max'),
                ),
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
    double thickness = 2.5,
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
            top: from.dy - thickness / 2,
            child: Transform.rotate(
              alignment: Alignment.centerLeft,
              angle: math.atan2(segment.dy, segment.dx),
              child: Container(
                width: segment.distance,
                height: thickness,
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

class _ExplanationGroup extends StatelessWidget {
  const _ExplanationGroup({required this.title, required this.explanations});

  final String title;
  final List<String> explanations;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        title,
        style: Theme.of(context).textTheme.titleSmall
            ?.copyWith(fontWeight: FontWeight.bold),
      ),
      const SizedBox(height: 8),
      for (final explanation in explanations)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Icon(Icons.circle, size: 6),
              ),
              const SizedBox(width: 10),
              Expanded(child: Text(explanation)),
            ],
          ),
        ),
    ],
  );
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
