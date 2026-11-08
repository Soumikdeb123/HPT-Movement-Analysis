import 'package:flutter/foundation.dart';

import '../models/analysis_request.dart';
import '../models/analysis_result.dart';
import '../repositories/analysis_gateway.dart';
import '../repositories/http_analysis_gateway.dart';
import '../services/analysis_video_picker.dart';

enum AnalysisStatus {
  idle,
  selectingVideo,
  videoSelected,
  validating,
  processing,
  cancelling,
  completed,
  clearingResult,
  failed,
}

class AnalysisViewModel extends ChangeNotifier {
  AnalysisViewModel(this._gateway, this._videoPicker);

  final AnalysisGateway _gateway;
  final AnalysisVideoPicker _videoPicker;

  AnalysisStatus status = AnalysisStatus.idle;
  SelectedVideo? selectedVideo;
  double progress = 0;
  AnalysisResult? result;
  InputVideoMetadata? validatedVideoMetadata;
  String? errorMessage;
  TargetPlayerPosition targetPlayer = TargetPlayerPosition.nearCourt;
  double? athleteMassKg;
  String? massError;
  AnalysisCancellationToken? _cancellationToken;
  int _operationGeneration = 0;

  bool get isProcessing =>
      status == AnalysisStatus.validating ||
      status == AnalysisStatus.processing ||
      status == AnalysisStatus.cancelling;
  bool get isValidating => status == AnalysisStatus.validating;
  bool get isCancelling => status == AnalysisStatus.cancelling;
  bool get isClearingResult => status == AnalysisStatus.clearingResult;
  bool get isSelectingVideo => status == AnalysisStatus.selectingVideo;
  bool get canStart =>
      selectedVideo != null &&
      !isProcessing &&
      !isSelectingVideo &&
      !isClearingResult &&
      massError == null;
  PlayerAnalysis? get selectedPlayer {
    final players = result?.players;
    return players == null || players.isEmpty ? null : players.first;
  }

  Future<void> selectVideo() async {
    if (isProcessing || isSelectingVideo || isClearingResult) return;

    final previousStatus = status;
    status = AnalysisStatus.selectingVideo;
    errorMessage = null;
    notifyListeners();

    try {
      final video = await _videoPicker.pickVideo();
      if (video == null) {
        status = selectedVideo == null
            ? AnalysisStatus.idle
            : AnalysisStatus.videoSelected;
        notifyListeners();
        return;
      }

      selectedVideo = video;
      result = null;
      validatedVideoMetadata = null;
      progress = 0;
      status = AnalysisStatus.videoSelected;
    } on Object catch (error) {
      status = previousStatus == AnalysisStatus.completed
          ? AnalysisStatus.completed
          : AnalysisStatus.failed;
      errorMessage = 'Could not select the video. $error';
    }
    notifyListeners();
  }

  void selectTargetPlayer(Set<TargetPlayerPosition> selection) {
    if (selection.isEmpty || isProcessing) return;
    targetPlayer = selection.first;
    notifyListeners();
  }

  void updateAthleteMass(String value) {
    final parsed = double.tryParse(value.trim());
    athleteMassKg =
        parsed != null && parsed.isFinite && parsed >= 20 && parsed <= 250
        ? parsed
        : null;
    massError = value.trim().isNotEmpty && athleteMassKg == null
        ? 'Enter 20–250 kg, or leave blank to analyse movement without force.'
        : null;
    notifyListeners();
  }

  Future<void> startAnalysis() async {
    final video = selectedVideo;
    final massKg = athleteMassKg;
    if (video == null || !canStart) return;

    status = AnalysisStatus.validating;
    progress = 0;
    result = null;
    validatedVideoMetadata = null;
    errorMessage = null;
    notifyListeners();

    final operationGeneration = ++_operationGeneration;
    final cancellationToken = AnalysisCancellationToken();
    _cancellationToken = cancellationToken;

    try {
      final completedResult = await _gateway.analyseVideo(
        AnalysisRequest(
          videoPath: video.path,
          videoName: video.name,
          targetPlayer: targetPlayer,
          athleteMassKg: massKg,
        ),
        onVideoValidated: (metadata) {
          if (operationGeneration != _operationGeneration) return;
          validatedVideoMetadata = metadata;
          status = AnalysisStatus.processing;
          notifyListeners();
        },
        onProgress: (value) {
          if (operationGeneration != _operationGeneration) return;
          // Keep compatibility with older servers that do not return the new
          // metadata object, while still leaving the validation phase.
          if (status == AnalysisStatus.validating) {
            status = AnalysisStatus.processing;
          }
          progress = value.clamp(0, 1);
          notifyListeners();
        },
        cancellationToken: cancellationToken,
      );
      if (operationGeneration != _operationGeneration) return;
      result = completedResult;
      validatedVideoMetadata =
          completedResult.inputVideo ?? validatedVideoMetadata;
      progress = 1;
      status = AnalysisStatus.completed;
    } on AnalysisCancelledException {
      if (operationGeneration != _operationGeneration) return;
      _resetFields();
    } on AnalysisGatewayException catch (error) {
      if (operationGeneration != _operationGeneration) return;
      status = AnalysisStatus.failed;
      errorMessage = error.message;
    } on Object catch (error) {
      if (operationGeneration != _operationGeneration) return;
      status = AnalysisStatus.failed;
      errorMessage = 'Analysis failed unexpectedly. $error';
    }

    if (operationGeneration == _operationGeneration) {
      _cancellationToken = null;
    }
    notifyListeners();
  }

  Future<void> cancelAnalysis() async {
    final cancellationToken = _cancellationToken;
    if (cancellationToken == null || !isProcessing || isCancelling) return;

    status = AnalysisStatus.cancelling;
    notifyListeners();
    ++_operationGeneration;
    try {
      await _gateway.cancelAnalysis(cancellationToken);
      _cancellationToken = null;
      _resetFields();
    } on Object catch (error) {
      status = AnalysisStatus.failed;
      errorMessage = 'Could not cancel the analysis. $error';
    }
    notifyListeners();
  }

  Future<void> clearAnalysis() async {
    final completedResult = result;
    if (completedResult == null || isClearingResult) return;

    status = AnalysisStatus.clearingResult;
    notifyListeners();
    await Future<void>.delayed(Duration.zero);
    try {
      await _gateway.deleteAnalysis(completedResult.analysisId);
      _resetFields();
    } on Object catch (error) {
      status = AnalysisStatus.completed;
      errorMessage = 'Could not clear the saved result. $error';
    }
    notifyListeners();
  }

  void reset() {
    ++_operationGeneration;
    _cancellationToken?.requestCancellation();
    _cancellationToken = null;
    _resetFields();
    notifyListeners();
  }

  void _resetFields() {
    status = AnalysisStatus.idle;
    selectedVideo = null;
    progress = 0;
    result = null;
    validatedVideoMetadata = null;
    errorMessage = null;
    targetPlayer = TargetPlayerPosition.nearCourt;
    // The mass field remains mounted after clearing a result, so retain its value.
  }

  bool _disposed = false;
  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    ++_operationGeneration;
    _cancellationToken?.requestCancellation();
    super.dispose();
  }
}
