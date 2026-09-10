import '../models/analysis_request.dart';
import '../models/analysis_result.dart';

typedef ProgressCallback = void Function(double progress);

class AnalysisCancellationToken {
  bool _isCancellationRequested = false;
  bool _cancellationSent = false;
  String? _analysisId;

  bool get isCancellationRequested => _isCancellationRequested;
  String? get analysisId => _analysisId;

  void requestCancellation() => _isCancellationRequested = true;

  void attachAnalysisId(String analysisId) => _analysisId = analysisId;

  bool beginCancellationRequest() {
    if (!_isCancellationRequested || _analysisId == null || _cancellationSent) {
      return false;
    }
    _cancellationSent = true;
    return true;
  }
}

class AnalysisCancelledException implements Exception {
  const AnalysisCancelledException();
}

abstract interface class AnalysisGateway {
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
  });

  Future<void> cancelAnalysis(AnalysisCancellationToken cancellationToken);

  Future<void> deleteAnalysis(String analysisId);
}
