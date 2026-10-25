import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/analysis_result.dart';

class ForceVelocityChart extends StatelessWidget {
  const ForceVelocityChart({super.key, required this.analysis});

  final ForceVelocityAnalysis analysis;

  @override
  Widget build(BuildContext context) {
    final available =
        analysis.status == MetricStatus.experimental &&
        analysis.samples.length >= 2;
    final colors = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.show_chart),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Estimated Force–Velocity',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                _StatusLabel(status: analysis.status),
              ],
            ),
            const SizedBox(height: 12),
            if (available) ...[
              SizedBox(
                height: 250,
                child: CustomPaint(
                  key: const Key('force-velocity-chart'),
                  painter: _ForceVelocityPainter(
                    samples: analysis.samples,
                    propulsiveColor: colors.primary,
                    brakingColor: colors.error,
                    steadyColor: colors.outline,
                    gridColor: colors.outlineVariant,
                    labelColor: colors.onSurfaceVariant,
                  ),
                  child: const SizedBox.expand(),
                ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 16,
                runSpacing: 8,
                children: [
                  _LegendDot(color: colors.primary, label: 'Propulsive'),
                  _LegendDot(color: colors.error, label: 'Braking'),
                  _LegendDot(color: colors.outline, label: 'Near steady'),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 20,
                runSpacing: 6,
                children: [
                  _Summary(
                    label: 'Max velocity',
                    value: _value(analysis.maximumVelocityMps, 'm/s'),
                  ),
                  _Summary(
                    label: 'Peak propulsive',
                    value: _value(analysis.peakPropulsiveForceN, 'N'),
                  ),
                  _Summary(
                    label: 'Peak braking',
                    value: _value(analysis.peakBrakingForceN, 'N'),
                  ),
                ],
              ),
            ] else
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.info_outline),
                title: const Text('Metric Force–Velocity is not available'),
                subtitle: Text(
                  analysis.note ?? 'The court mapping or metric trajectory was not reliable enough.',
                ),
              ),
            const SizedBox(height: 10),
            Text(
              available ? analysis.note ?? '' : 'Movement results remain available above in the units shown.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  static String _value(double? value, String unit) =>
      value == null ? '—' : '${value.toStringAsFixed(1)} $unit';
}

class _StatusLabel extends StatelessWidget {
  const _StatusLabel({required this.status});

  final MetricStatus status;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final available = status == MetricStatus.experimental;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: available
            ? colors.tertiaryContainer
            : colors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        available ? 'Estimated' : 'Unavailable',
        style: Theme.of(context).textTheme.labelSmall,
      ),
    );
  }
}

class _LegendDot extends StatelessWidget {
  const _LegendDot({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 9,
          height: 9,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 5),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelMedium),
        Text(value, style: Theme.of(context).textTheme.titleSmall),
      ],
    );
  }
}

class _ForceVelocityPainter extends CustomPainter {
  _ForceVelocityPainter({
    required this.samples,
    required this.propulsiveColor,
    required this.brakingColor,
    required this.steadyColor,
    required this.gridColor,
    required this.labelColor,
  });

  final List<ForceVelocitySample> samples;
  final Color propulsiveColor;
  final Color brakingColor;
  final Color steadyColor;
  final Color gridColor;
  final Color labelColor;

  @override
  void paint(Canvas canvas, Size size) {
    const left = 48.0;
    const top = 10.0;
    const right = 12.0;
    const bottom = 32.0;
    final plot = Rect.fromLTRB(
      left,
      top,
      size.width - right,
      size.height - bottom,
    );
    if (plot.width <= 0 || plot.height <= 0) return;

    final maximumVelocity = math.max(
      1.0,
      samples.map((sample) => sample.velocityMps).reduce(math.max) * 1.08,
    );
    final maximumForce = math.max(
      100.0,
      samples
              .map((sample) => sample.estimatedNetForceN.abs())
              .reduce(math.max) *
          1.12,
    );

    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    for (var index = 0; index <= 4; index++) {
      final x = plot.left + plot.width * index / 4;
      final y = plot.top + plot.height * index / 4;
      canvas.drawLine(Offset(x, plot.top), Offset(x, plot.bottom), gridPaint);
      canvas.drawLine(Offset(plot.left, y), Offset(plot.right, y), gridPaint);
    }

    final zeroY = plot.top + plot.height / 2;
    canvas.drawLine(
      Offset(plot.left, zeroY),
      Offset(plot.right, zeroY),
      Paint()
        ..color = labelColor
        ..strokeWidth = 1.5,
    );

    for (final sample in samples) {
      final x = plot.left + sample.velocityMps / maximumVelocity * plot.width;
      final y =
          zeroY - sample.estimatedNetForceN / maximumForce * plot.height / 2;
      final color = switch (sample.phase) {
        'propulsive' => propulsiveColor,
        'braking' => brakingColor,
        _ => steadyColor,
      };
      canvas.drawCircle(Offset(x, y), 2.6, Paint()..color = color);
    }

    _label(canvas, 'Force (N)', Offset(0, plot.top), labelColor);
    _label(
      canvas,
      'Velocity (m/s)',
      Offset(plot.right - 82, plot.bottom + 10),
      labelColor,
    );
    _label(canvas, '0', Offset(plot.left - 14, zeroY - 7), labelColor);
    _label(
      canvas,
      maximumVelocity.toStringAsFixed(1),
      Offset(plot.right - 18, plot.bottom + 10),
      labelColor,
    );
  }

  static void _label(Canvas canvas, String text, Offset offset, Color color) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(fontSize: 10, color: color),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, offset);
  }

  @override
  bool shouldRepaint(covariant _ForceVelocityPainter oldDelegate) =>
      oldDelegate.samples != samples ||
      oldDelegate.propulsiveColor != propulsiveColor ||
      oldDelegate.brakingColor != brakingColor ||
      oldDelegate.gridColor != gridColor;
}
