import 'package:flutter/foundation.dart';

import '../models/analysis_request.dart';
import '../models/analysis_result.dart';
import '../repositories/analysis_gateway.dart';

enum AnalysisStatus { idle, videoSelected, processing, completed, failed }

class AnalysisViewModel extends ChangeNotifier {
  AnalysisViewModel(this._gateway);

  final AnalysisGateway _gateway;

  AnalysisStatus status = AnalysisStatus.idle;
  String? videoPath;
  String selectedPlayer = 'Player 1';
  bool includeExperimentalSpeed = true;
  double progress = 0;
  AnalysisResult? result;
  String? errorMessage;

  bool get isProcessing => status == AnalysisStatus.processing;

  bool get canStart => videoPath != null && !isProcessing;

  void selectPrototypeVideo() {
    videoPath = 'sample_tennis_match.mp4';
    status = AnalysisStatus.videoSelected;
    result = null;
    errorMessage = null;
    notifyListeners();
  }

  void selectPlayer(String? player) {
    if (player == null || player == selectedPlayer) return;
    selectedPlayer = player;
    notifyListeners();
  }

  void setExperimentalSpeed(bool enabled) {
    includeExperimentalSpeed = enabled;
    notifyListeners();
  }

  Future<void> startAnalysis() async {
    final selectedVideo = videoPath;
    if (selectedVideo == null || isProcessing) return;

    status = AnalysisStatus.processing;
    progress = 0;
    result = null;
    errorMessage = null;
    notifyListeners();

    try {
      result = await _gateway.analyseVideo(
        AnalysisRequest(
          videoPath: selectedVideo,
          playerLabel: selectedPlayer,
          includeExperimentalSpeed: includeExperimentalSpeed,
        ),
        onProgress: (value) {
          progress = value.clamp(0, 1);
          notifyListeners();
        },
      );
      status = AnalysisStatus.completed;
    } on Object {
      status = AnalysisStatus.failed;
      errorMessage = 'Analysis failed. Please try again.';
    }

    notifyListeners();
  }

  void reset() {
    status = AnalysisStatus.idle;
    videoPath = null;
    selectedPlayer = 'Player 1';
    includeExperimentalSpeed = true;
    progress = 0;
    result = null;
    errorMessage = null;
    notifyListeners();
  }
}
