import 'dart:math' as math;

import 'package:flutter/material.dart';

class AccelerationChart extends StatefulWidget {
  const AccelerationChart({
    super.key,
    required this.frameNumbers,
    required this.accelerationValues,
    required this.fps,
    this.isPrototype = false,
  });
  
  // 从真实分析结果创建曲线
  factory AccelerationChart.fromTrackingData({
    Key? key,
    required Map<String, dynamic> trackingData,
    required String trackId,
  }) {
    final rawFps = trackingData['video_fps'];
    final fps = rawFps is num ? rawFps.toDouble() : 0.0;

    final tracks = trackingData['tracks'];
    final track = tracks is Map ? tracks[trackId] : null;

    final frames = <int>[];
    final accelerations = <double?>[];

  if (trackingData['court_calibrated'] == true &&
      fps.isFinite &&
      fps > 0 &&
      track is Map) {
    final rawFrames = track['frame_numbers'];
    final rawAccelerations = track['acceleration_mps2'];

    if (rawFrames is List &&
        rawAccelerations is List &&
        rawFrames.length == rawAccelerations.length) {
      for (var i = 0; i < rawFrames.length; i++) {
        final frame = rawFrames[i];
        final acceleration = rawAccelerations[i];

        // 无效帧号无法确定横轴时间
        if (frame is! num ||
            !frame.isFinite ||
            frame < 0 ||
            frame != frame.roundToDouble()) {
          continue;
        }

        frames.add(frame.toInt());

        // 保留缺失数据，让曲线在缺失位置断开
        accelerations.add(
          acceleration is num && acceleration.isFinite
              ? acceleration.toDouble()
              : null,
        );
      }
    }
  }

  return AccelerationChart(
    key: key,
    frameNumbers: frames,
    accelerationValues: accelerations,
    fps: fps,
    isPrototype: false,
  );
}

  final List<int> frameNumbers;
  final List<double?> accelerationValues;
  final double fps;
  final bool isPrototype;

  @override
  State<AccelerationChart> createState() => _AccelerationChartState();
}

class _AccelerationChartState extends State<AccelerationChart> {
  int? selectedIndex;

  @override
  void didUpdateWidget(covariant AccelerationChart oldWidget) {
    super.didUpdateWidget(oldWidget);
    selectedIndex = null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final validInput = widget.fps.isFinite &&
        widget.fps > 0 &&
        widget.frameNumbers.length == widget.accelerationValues.length;

    final samples = <_Sample>[];

    if (validInput) {
      for (var i = 0; i < widget.frameNumbers.length; i++) {
        final value = widget.accelerationValues[i];

        samples.add(
          _Sample(
            widget.frameNumbers[i] / widget.fps,
            value != null && value.isFinite ? value : null,
          ),
        );
      }

      samples.sort((a, b) => a.time.compareTo(b.time));
    }

    final hasData = samples.any((sample) => sample.value != null);

    final selected = selectedIndex != null &&
            selectedIndex! < samples.length
        ? samples[selectedIndex!]
        : null;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  'Acceleration',
                  style: theme.textTheme.titleLarge,
                ),
                if (widget.isPrototype)
                  const Chip(label: Text('Mock data')),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Acceleration over time',
              style: theme.textTheme.bodyLarge,
            ),
            const SizedBox(height: 20),

            if (!hasData)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Text(
                  'No acceleration data available.',
                  textAlign: TextAlign.center,
                ),
              )
            else ...[
              Text(
                'Acceleration (m/s²)',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 8),

              LayoutBuilder(
                builder: (context, constraints) {
                  return GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTapDown: (details) {
                      final width = constraints.maxWidth - 76;
                      if (width <= 0) return;

                      final fraction = (
                        (details.localPosition.dx - 56) / width
                      ).clamp(0.0, 1.0);

                      final start = samples.first.time;
                      final span = samples.last.time - start;
                      final target = start + span * fraction;

                      var nearest = 0;

                      for (var i = 1; i < samples.length; i++) {
                        if ((samples[i].time - target).abs() <
                            (samples[nearest].time - target).abs()) {
                          nearest = i;
                        }
                      }

                      setState(() => selectedIndex = nearest);
                    },
                    child: SizedBox(
                      height: 240,
                      width: double.infinity,
                      child: CustomPaint(
                        painter: _AccelerationPainter(
                          samples: samples,
                          selectedIndex: selectedIndex,
                          lineColor: theme.colorScheme.primary,
                          textColor: theme.colorScheme.onSurface,
                          gridColor: theme.colorScheme.outlineVariant,
                        ),
                      ),
                    ),
                  );
                },
              ),

              Text(
                'Time (s)',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),

              DecoratedBox(
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      const Icon(Icons.timeline_outlined),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          selected == null
                              ? 'Tap the chart to view acceleration.'
                              : '${selected.time.toStringAsFixed(2)} s'
                                  '  ·  '
                                  '${selected.value == null ? "Unavailable" : "${selected.value!.toStringAsFixed(2)} m/s²"}',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Sample {
  const _Sample(this.time, this.value);

  final double time;
  final double? value;
}

class _AccelerationPainter extends CustomPainter {
  _AccelerationPainter({
    required this.samples,
    required this.selectedIndex,
    required this.lineColor,
    required this.textColor,
    required this.gridColor,
  });

  final List<_Sample> samples;
  final int? selectedIndex;
  final Color lineColor;
  final Color textColor;
  final Color gridColor;

  @override
  void paint(Canvas canvas, Size size) {
    final plot = Rect.fromLTRB(
      56,
      12,
      size.width - 20,
      size.height - 28,
    );

    if (plot.width <= 0 || plot.height <= 0) return;

    var minValue = 0.0;
    var maxValue = 0.0;

    for (final sample in samples) {
      final value = sample.value;
      if (value == null) continue;

      minValue = math.min(minValue, value);
      maxValue = math.max(maxValue, value);
    }

    // 给曲线上下留出空间；全部为 0 时也能正常显示
    final margin = math.max((maxValue - minValue) * 0.15, 0.5);
    minValue -= margin;
    maxValue += margin;

    final startTime = samples.first.time;
    final endTime = samples.last.time;

    // 单个样本时放在图表中央
    final timeMin = endTime > startTime ? startTime : startTime - 0.5;
    final timeMax = endTime > startTime ? endTime : startTime + 0.5;

    double xFor(double time) {
      return plot.left +
          (time - timeMin) / (timeMax - timeMin) * plot.width;
    }

    double yFor(double value) {
      return plot.bottom -
          (value - minValue) / (maxValue - minValue) * plot.height;
    }

    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;

    // 横向网格与加速度刻度
    for (var i = 0; i <= 4; i++) {
      final value = minValue + (maxValue - minValue) * i / 4;
      final y = yFor(value);

      canvas.drawLine(
        Offset(plot.left, y),
        Offset(plot.right, y),
        gridPaint,
      );

      _label(
        canvas,
        value.toStringAsFixed(1),
        Offset(plot.left - 8, y - 7),
        rightAligned: true,
      );
    }

    // 时间刻度
    for (var i = 0; i <= 4; i++) {
      final time = timeMin + (timeMax - timeMin) * i / 4;

      _label(
        canvas,
        time.toStringAsFixed(1),
        Offset(xFor(time), plot.bottom + 8),
        centered: true,
      );
    }

    // 零参考线
    canvas.drawLine(
      Offset(plot.left, yFor(0)),
      Offset(plot.right, yFor(0)),
      Paint()
        ..color = textColor.withValues(alpha: 0.45)
        ..strokeWidth = 1.2,
    );

    canvas.save();
    canvas.clipRect(plot.inflate(4));

    final linePaint = Paint()
      ..color = lineColor
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    Offset? previousPoint;

    for (final sample in samples) {
      final value = sample.value;

      // 数据缺失时断开曲线，不能当成 0
      if (value == null) {
        previousPoint = null;
        continue;
      }

      final point = Offset(
        xFor(sample.time),
        yFor(value),
      );

      if (previousPoint != null) {
        canvas.drawLine(previousPoint, point, linePaint);
      }

      canvas.drawCircle(
        point,
        2,
        Paint()..color = lineColor,
      );

      previousPoint = point;
    }

    final index = selectedIndex;

    if (index != null && index < samples.length) {
      final sample = samples[index];
      final x = xFor(sample.time);

      canvas.drawLine(
        Offset(x, plot.top),
        Offset(x, plot.bottom),
        Paint()
          ..color = textColor.withValues(alpha: 0.5)
          ..strokeWidth = 1,
      );

      if (sample.value != null) {
        canvas.drawCircle(
          Offset(x, yFor(sample.value!)),
          5,
          Paint()..color = lineColor,
        );
      }
    }

    canvas.restore();
  }

  void _label(
    Canvas canvas,
    String text,
    Offset position, {
    bool centered = false,
    bool rightAligned = false,
  }) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: textColor,
          fontSize: 10,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();

    final x = rightAligned
        ? position.dx - painter.width
        : centered
            ? position.dx - painter.width / 2
            : position.dx;

    painter.paint(canvas, Offset(x, position.dy));
  }

  @override
  bool shouldRepaint(covariant _AccelerationPainter oldDelegate) {
    return true;
  }
}