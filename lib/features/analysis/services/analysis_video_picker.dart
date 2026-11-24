import 'dart:io';

import 'package:image_picker/image_picker.dart';

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
    final picker = ImagePicker();

    final video = await picker.pickVideo(
      source: ImageSource.gallery,
    );

    if (video == null) return null;

    final file = File(video.path);
    final sizeBytes = await file.length();

    return SelectedVideo(
      path: video.path,
      name: video.name,
      sizeBytes: sizeBytes,
    );
  }
}
