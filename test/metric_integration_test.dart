import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/core/config/api_endpoints.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/views/acceleration_chart.dart';
import 'package:hpt_player_analysis/features/analysis/views/force_velocity_chart.dart';

void main() {
  test('API defaults distinguish Android from Apple simulators', () {
    expect(ApiEndpoints.defaultHost(TargetPlatform.android), '10.0.2.2');
    expect(ApiEndpoints.defaultHost(TargetPlatform.iOS), '127.0.0.1');
  });
  test('metric samples preserve missing values and segment boundaries', () {
    final m = NumericMetric.fromJson({
      'status': 'experimental',
      'unit': 'm/s²',
      'value': 2,
      'samples': [
        {'timeSeconds': 1, 'value': -2, 'segmentId': 3},
        {'timeSeconds': 2, 'value': double.nan, 'segmentId': 4},
        {'timeSeconds': double.nan, 'value': 7},
      ],
    });
    expect(m.samples.length, 2);
    expect(m.samples.first.value, -2);
    expect(m.samples.last.value, isNull);
    expect(m.samples.last.segmentId, 4);
  });
  test('invalid force samples are omitted, not converted into zeros', () {
    final f = ForceVelocityAnalysis.fromJson({
      'status': 'experimental',
      'samples': [
        {
          'timeSeconds': 1,
          'velocityMps': double.nan,
          'tangentialAccelerationMps2': 2,
          'estimatedNetForceN': 140,
        },
        {
          'timeSeconds': 1,
          'velocityMps': 3,
          'tangentialAccelerationMps2': 2,
          'estimatedNetForceN': 140,
        },
      ],
    });
    expect(f.samples.length, 1);
  });
  testWidgets(
    'real signed curve renders in pixel units and supports inspection',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: AccelerationChart(
              unit: 'px/s²',
              samples: [
                MetricSample(0, -2),
                MetricSample(.1, 3),
                MetricSample(.2, null),
                MetricSample(2, -4, segmentId: 1),
              ],
            ),
          ),
        ),
      );
      expect(find.text('Value (px/s²)'), findsOneWidget);
      expect(find.text('Mock data'), findsNothing);
      await tester.tapAt(const Offset(200, 200));
      await tester.pump();
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'force plot explains unavailable data without inventing results',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ForceVelocityChart(
              analysis: ForceVelocityAnalysis.unavailable(),
            ),
          ),
        ),
      );
      expect(
        find.text('Estimated Force-Velocity'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('force-velocity-chart')), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
