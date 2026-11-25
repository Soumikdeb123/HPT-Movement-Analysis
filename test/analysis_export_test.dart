import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/services/analysis_export_service.dart';

void main() {
  test('exports a compact readable summary without raw samples', () {
    final result = AnalysisResult.fromJson({
      'playerName': 'Alan',
      'selectedTrackId': '1',
      'players': [
        {
          'trackId': '1',
          'trackedFrames': 90,
          'coverageFrameCount': 100,
          'leftRightDistance': {
            'value': 3,
            'unit': 'm',
            'status': 'calibrated',
          },
          'totalDistance': {'value': 12.5, 'unit': 'm', 'status': 'calibrated'},
          'speed': {
            'average': 1.2,
            'peak': 3.8,
            'unit': 'm/s',
            'samples': [
              {'timeSeconds': 1, 'value': 5},
            ],
          },
          'overallEffort': {
            'status': 'experimental',
            'method': 'metric_motion_load_v1',
            'value': 8.5,
            'unit': 'AU',
            'validSeconds': 25,
            'speedAU': 3.2,
            'accelerationAU': 2.7,
            'brakingAU': 2.6,
            'auPerValidMinute': 20.4,
          },
          'forceVelocity': {
            'status': 'experimental',
            'massKg': 75,
            'comparisonSummary': 'Below usual overall',
            'currentCurve': [
              {'velocityMps': 0.2, 'forceNPerKg': 1.7},
              {'velocityMps': 1.0, 'forceNPerKg': 1.2},
            ],
            'baselineCurve': [
              {'velocityMps': 0.2, 'forceNPerKg': 1.8},
              {'velocityMps': 1.0, 'forceNPerKg': 1.3},
            ],
            'events': [
              {
                'eventId': 'event-1',
                'label': 'Highest movement speed',
                'startTimeSeconds': 12.3,
                'endTimeSeconds': 13.1,
                'videoSeekStartSeconds': 11.8,
                'videoSeekEndSeconds': 14,
                'startSpeedMps': 1.0,
                'peakSpeedMps': 3.8,
                'meanForceNPerKg': 1.4,
                'startX': 1,
                'startY': 2,
                'endX': 3,
                'endY': 4,
              },
            ],
            'samples': [
              {
                'timeSeconds': 1,
                'velocityMps': 4.2,
                'tangentialAccelerationMps2': 2,
              },
            ],
          },
        },
      ],
    }, analysisId: 'job-1');
    final csv = AnalysisExportService().csvText(result);

    expect(
      csv,
      startsWith(
        '"Section","Metric","Video time","Speed / range","This session","Personal baseline","Difference","Unit"',
      ),
    );
    expect(csv, contains('"Session","Body mass"'));
    expect(csv, contains('"Force-Velocity","Peak estimated propulsion"'));
    expect(csv, contains('"Key movement moments","Highest movement speed"'));
    expect(csv, contains('"Overall effort","Total load"'));
    expect(csv, isNot(contains('speed_sample')));
    expect(csv, isNot(contains('track_id')));
    expect(csv, isNot(contains('segment_id')));
    expect(csv, isNot(contains('Savitzky')));
    expect(csv.split('\r\n').length, lessThan(50));
  });
}
