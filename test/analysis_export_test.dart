import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/services/analysis_export_service.dart';

void main() {
  test('exports retain metric units, unavailable values and raw trajectory samples', () {
    final result = AnalysisResult.fromJson({
      'players': [
        {
          'trackId': '1',
          'leftRightDistance': {
            'value': 3,
            'unit': 'px',
            'status': 'experimental',
          },
          'speed': {
            'samples': [
              {'timeSeconds': 1, 'value': 5},
            ],
          },
          'overallEffort': {'status': 'unavailable'},
          'forceVelocity': {
            'status': 'experimental',
            'maximumVelocityMps': 4.2,
            'peakPropulsiveForceN': 120,
            'peakBrakingForceN': 90,
            'samples': [
              {'timeSeconds': 1, 'velocityMps': 4.2, 'estimatedNetForceN': 120},
            ],
          },
        },
      ],
    }, analysisId: 'job-1');
    final service = AnalysisExportService();
    final csv = service.csvText(result);
    expect(csv, contains('"left_right_distance","3.0","px","experimental"'));
    expect(csv, isNot(contains('"overall_effort"')));
    expect(csv, contains('"estimated_peak_propulsive_force","120.0","N"'));
    final json = jsonDecode(service.jsonText(result));
    expect(json['analysisId'], 'job-1');
    expect(json['players'][0]['speed']['samples'][0]['value'], 5);
  });
}
