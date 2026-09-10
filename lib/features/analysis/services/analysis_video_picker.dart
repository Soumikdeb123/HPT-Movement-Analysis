import 'package:file_picker/file_picker.dart';

class SelectedVideo {
  const SelectedVideo({
    required this.path,
    required this.name,
    required this.sizeBytes,
  });

  final String path;
  final String name;
  final int sizeBytes;
}

abstract interface class AnalysisVideoPicker {
  Future<SelectedVideo?> pickVideo();
}

class FilePickerAnalysisVideoPicker implements AnalysisVideoPicker {
  const FilePickerAnalysisVideoPicker();

  @override
  Future<SelectedVideo?> pickVideo() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['mp4', 'mov', 'avi', 'mkv'],
      allowMultiple: false,
      withData: false,
    );
    if (result == null) return null;

    final file = result.files.single;
    final path = file.path;
    if (path == null || path.isEmpty) {
      throw StateError('The selected video is not available as a local file.');
    }
    return SelectedVideo(path: path, name: file.name, sizeBytes: file.size);
  }
}
