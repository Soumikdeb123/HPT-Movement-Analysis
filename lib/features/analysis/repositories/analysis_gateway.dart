import '../models/analysis_request.dart';
import '../models/analysis_result.dart';

typedef ProgressCallback = void Function(double progress);

abstract interface class AnalysisGateway {
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
  });
}
