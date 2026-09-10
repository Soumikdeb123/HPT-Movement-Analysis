import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/services/analysis_video_picker.dart';
import 'package:hpt_player_analysis/features/analysis/view_models/analysis_view_model.dart';

void main() {
  test('analysis progresses from a selected real file to a result', () async {
    final viewModel = AnalysisViewModel(
      _ImmediateGateway(),
      const _FakeVideoPicker(),
    );

    expect(viewModel.canStart, isFalse);

    await viewModel.selectVideo();
    expect(viewModel.canStart, isTrue);
    expect(viewModel.selectedVideo?.name, 'client-video.mp4');

    await viewModel.startAnalysis();

    expect(viewModel.status, AnalysisStatus.completed);
    expect(viewModel.progress, 1);
    expect(viewModel.selectedPlayer?.totalDistance.value, 500);
    expect(viewModel.selectedPlayer?.totalDistance.unit, 'px');

    await viewModel.clearAnalysis();
    expect(viewModel.status, AnalysisStatus.idle);
    expect(viewModel.result, isNull);
  });

  test('cancelled file selection leaves the view model idle', () async {
    final viewModel = AnalysisViewModel(
      _ImmediateGateway(),
      const _CancelledVideoPicker(),
    );

    await viewModel.selectVideo();

    expect(viewModel.status, AnalysisStatus.idle);
    expect(viewModel.selectedVideo, isNull);
  });

  test('running analysis can be cancelled and reset to idle', () async {
    final gateway = _CancellableGateway();
    final viewModel = AnalysisViewModel(gateway, const _FakeVideoPicker());
    await viewModel.selectVideo();

    final runningAnalysis = viewModel.startAnalysis();
    expect(viewModel.status, AnalysisStatus.processing);

    await viewModel.cancelAnalysis();
    await runningAnalysis;

    expect(gateway.cancelCalled, isTrue);
    expect(viewModel.status, AnalysisStatus.idle);
    expect(viewModel.selectedVideo, isNull);
    expect(viewModel.result, isNull);
  });
}

class _FakeVideoPicker implements AnalysisVideoPicker {
  const _FakeVideoPicker();

  @override
  Future<SelectedVideo?> pickVideo() async {
    return const SelectedVideo(
      path: 'C:/videos/client-video.mp4',
      name: 'client-video.mp4',
      sizeBytes: 1024,
    );
  }
}

class _CancelledVideoPicker implements AnalysisVideoPicker {
  const _CancelledVideoPicker();

  @override
  Future<SelectedVideo?> pickVideo() async => null;
}

class _ImmediateGateway implements AnalysisGateway {
  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
  }) async {
    expect(request.videoName, 'client-video.mp4');
    onProgress(0.5);
    onProgress(1);
    return _testResult;
  }

  @override
  Future<void> cancelAnalysis(
    AnalysisCancellationToken cancellationToken,
  ) async {
    cancellationToken.requestCancellation();
  }

  @override
  Future<void> deleteAnalysis(String analysisId) async {
    expect(analysisId, 'test-analysis');
  }
}

class _CancellableGateway implements AnalysisGateway {
  final Completer<AnalysisResult> _result = Completer<AnalysisResult>();
  bool cancelCalled = false;

  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
  }) {
    onProgress(0.25);
    return _result.future;
  }

  @override
  Future<void> cancelAnalysis(
    AnalysisCancellationToken cancellationToken,
  ) async {
    cancelCalled = true;
    cancellationToken.requestCancellation();
    _result.completeError(const AnalysisCancelledException());
  }

  @override
  Future<void> deleteAnalysis(String analysisId) async {}
}

final _testResult = AnalysisResult.fromJson(const {
  'calibrationStatus': 'uncalibrated',
  'selectedTrackId': '7',
  'players': [
    {
      'trackId': '7',
      'movementPath': {
        'status': 'experimental',
        'coordinateSystem': 'image_pixels',
        'points': [
          {'timeSeconds': 0.0, 'x': 0.0, 'y': 0.0},
          {'timeSeconds': 1.0, 'x': 3.0, 'y': 4.0},
        ],
      },
      'totalDistance': {'status': 'experimental', 'value': 500, 'unit': 'px'},
      'speed': {
        'status': 'experimental',
        'average': 12,
        'peak': 18,
        'unit': 'px/s',
      },
      'acceleration': {'status': 'unavailable'},
      'deceleration': {'status': 'unavailable'},
      'directionChanges': {'status': 'unavailable'},
    },
  ],
  'warnings': [],
}, analysisId: 'test-analysis');
