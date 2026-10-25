import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../auth/repositories/auth_repository.dart';
import '../services/analysis_export_service.dart';
import '../models/analysis_request.dart';
import '../models/analysis_result.dart';
import '../repositories/analysis_gateway.dart';
import '../repositories/http_analysis_gateway.dart';
import '../services/analysis_video_picker.dart';
import '../view_models/analysis_view_model.dart';
import 'force_velocity_chart.dart';
import 'acceleration_chart.dart';

class AnalysisPage extends StatefulWidget {
  const AnalysisPage({
    super.key,
    this.gateway,
    this.videoPicker,
    this.onSignOut,
  });

  final VoidCallback? onSignOut;

  final AnalysisGateway? gateway;
  final AnalysisVideoPicker? videoPicker;

  @override
  State<AnalysisPage> createState() => _AnalysisPageState();
}

class _AnalysisPageState extends State<AnalysisPage> {
  late final AnalysisGateway _gateway;
  late final bool _ownsGateway;
  late final AnalysisViewModel viewModel;

  @override
  void initState() {
    super.initState();
    _ownsGateway = widget.gateway == null;
    _gateway = widget.gateway ?? HttpAnalysisGateway();
    viewModel = AnalysisViewModel(
      _gateway,
      widget.videoPicker ?? const FilePickerAnalysisVideoPicker(),
    );
  }

  @override
  void dispose() {
    viewModel.dispose();
    if (_ownsGateway && _gateway is HttpAnalysisGateway) {
      _gateway.close();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: viewModel,
      builder: (context, child) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('HPT Player Analysis'),
            actions: [
              if (widget.onSignOut != null)
                IconButton(
                  tooltip: 'Sign out',
                  onPressed:
                      viewModel.isProcessing || viewModel.isClearingResult
                      ? null
                      : widget.onSignOut,
                  icon: const Icon(Icons.logout),
                ),
            ],
          ),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 900),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Analyse tennis movement',
                          style: Theme.of(context).textTheme.headlineMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Select a fixed-camera tennis video and send it to '
                          'the local player-tracking prototype.',
                          style: Theme.of(context).textTheme.bodyLarge,
                        ),
                        const SizedBox(height: 24),
                        _VideoCard(viewModel: viewModel),
                        if (viewModel.validatedVideoMetadata
                            case final metadata?) ...[
                          const SizedBox(height: 16),
                          _InputVideoMetadataCard(metadata: metadata),
                        ],
                        const SizedBox(height: 16),
                        _TargetPlayerCard(viewModel: viewModel),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          key: const Key('start-analysis-button'),
                          onPressed: viewModel.canStart
                              ? viewModel.startAnalysis
                              : null,
                          icon: const Icon(Icons.play_arrow),
                          label: const Text('Start analysis'),
                        ),
                        if (viewModel.isProcessing) ...[
                          const SizedBox(height: 24),
                          _ProgressPanel(
                            progress: viewModel.progress,
                            isValidating: viewModel.isValidating,
                            isCancelling: viewModel.isCancelling,
                            onCancel: viewModel.cancelAnalysis,
                          ),
                        ],
                        if (viewModel.status == AnalysisStatus.completed) ...[
                          const SizedBox(height: 24),
                          _ResultsPanel(viewModel: viewModel),
                          if (viewModel.errorMessage != null)
                            Text(
                              viewModel.errorMessage!,
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.error,
                              ),
                            ),
                          const SizedBox(height: 8),
                          TextButton(
                            key: const Key('clear-analysis-button'),
                            onPressed: viewModel.clearAnalysis,
                            child: const Text('Clear result and start over'),
                          ),
                        ],
                        if (viewModel.isClearingResult) ...[
                          const SizedBox(height: 24),
                          const Center(child: CircularProgressIndicator()),
                        ],
                        if (viewModel.status == AnalysisStatus.failed) ...[
                          const SizedBox(height: 24),
                          _ErrorPanel(
                            message:
                                viewModel.errorMessage ??
                                'An unexpected error occurred.',
                            onRetry: viewModel.selectedVideo == null
                                ? viewModel.selectVideo
                                : viewModel.startAnalysis,
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _VideoCard extends StatelessWidget {
  const _VideoCard({required this.viewModel});

  final AnalysisViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final selectedVideo = viewModel.selectedVideo;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '1. Select video',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            const Text(
              'Choose an authorised MP4, MOV, AVI or MKV file. The video is '
              'sent only to the local analysis service configured for this app.',
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              key: const Key('select-video-button'),
              onPressed: viewModel.isProcessing || viewModel.isSelectingVideo
                  ? null
                  : viewModel.selectVideo,
              icon: viewModel.isSelectingVideo
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.video_library_outlined),
              label: Text(
                selectedVideo == null ? 'Choose video' : 'Choose another video',
              ),
            ),
            if (selectedVideo != null) ...[
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.movie_outlined),
                title: Text(selectedVideo.name),
                subtitle: Text(
                  '${_formatFileSize(selectedVideo.sizeBytes)} • Ready for analysis',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  static String _formatFileSize(int bytes) {
    if (bytes >= 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '$bytes bytes';
  }
}

class _InputVideoMetadataCard extends StatelessWidget {
  const _InputVideoMetadataCard({required this.metadata});

  final InputVideoMetadata metadata;

  @override
  Widget build(BuildContext context) {
    final statusText = metadata.hasWarnings
        ? 'Compatible with warnings'
        : 'Compatible';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                metadata.hasWarnings
                    ? Icons.warning_amber_outlined
                    : Icons.verified_outlined,
              ),
              title: const Text('Video compatibility checked'),
              subtitle: Text(statusText),
            ),
            Text(
              '${metadata.codecName} • '
              '${metadata.widthPixels} × ${metadata.heightPixels} • '
              '${metadata.framesPerSecond.toStringAsFixed(1)} fps',
            ),
            const SizedBox(height: 4),
            Text(
              '${_formatDuration(metadata.durationSeconds)} • '
              '${metadata.frameCount} frames • '
              '${_VideoCard._formatFileSize(metadata.sizeBytes)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (metadata.warnings.isNotEmpty) ...[
              const SizedBox(height: 8),
              for (final warning in metadata.warnings)
                Text(
                  '• $warning',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ],
        ),
      ),
    );
  }

  static String _formatDuration(double seconds) {
    final totalSeconds = seconds.round();
    final minutes = totalSeconds ~/ 60;
    final remainder = totalSeconds % 60;
    return minutes == 0
        ? '$remainder s'
        : '$minutes:${remainder.toString().padLeft(2, '0')}';
  }
}

class _TargetPlayerCard extends StatelessWidget {
  const _TargetPlayerCard({required this.viewModel});

  final AnalysisViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '2. Athlete details',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            const Text(
              'For this fixed-camera prototype, choose the athlete by their '
              'court side at the start of the video.',
            ),
            const SizedBox(height: 16),
            SegmentedButton<TargetPlayerPosition>(
              key: const Key('target-player-selector'),
              segments: TargetPlayerPosition.values
                  .map(
                    (position) => ButtonSegment(
                      value: position,
                      label: Text(position.label),
                      icon: Icon(
                        position == TargetPlayerPosition.nearCourt
                            ? Icons.south
                            : Icons.north,
                      ),
                    ),
                  )
                  .toList(growable: false),
              selected: {viewModel.targetPlayer},
              onSelectionChanged:
                  viewModel.isProcessing || viewModel.selectedVideo == null
                  ? null
                  : viewModel.selectTargetPlayer,
            ),
            const SizedBox(height: 18),
            TextField(
              key: const Key('athlete-mass-field'),
              enabled: !viewModel.isProcessing,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              onChanged: viewModel.updateAthleteMass,
              decoration: InputDecoration(
                labelText: 'Athlete body mass (optional)',
                hintText: 'For example, 75',
                suffixText: 'kg',
                border: OutlineInputBorder(),
                helperText: 'Only needed for estimated force (20–250 kg).',
                errorText: viewModel.massError,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProgressPanel extends StatelessWidget {
  const _ProgressPanel({
    required this.progress,
    required this.isValidating,
    required this.isCancelling,
    required this.onCancel,
  });

  final double progress;
  final bool isValidating;
  final bool isCancelling;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final hasMeasuredProgress = progress > 0;
    final percentage = (progress * 100).round();

    return Semantics(
      label: 'Analysis progress',
      value: hasMeasuredProgress ? '$percentage percent' : 'Starting',
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                isCancelling
                    ? 'Cancelling analysis…'
                    : isValidating
                    ? 'Checking video compatibility…'
                    : hasMeasuredProgress
                    ? 'Processing video: $percentage%'
                    : 'Uploading and starting analysis…',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 12),
              LinearProgressIndicator(
                value: hasMeasuredProgress ? progress : null,
              ),
              const SizedBox(height: 8),
              Text(
                isValidating
                    ? 'The service is checking the codec, resolution, frame rate and sample frames.'
                    : 'Keep this screen open. Local processing may take several minutes.',
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                key: const Key('cancel-analysis-button'),
                onPressed: isCancelling ? null : onCancel,
                icon: const Icon(Icons.stop_circle_outlined),
                label: Text(isCancelling ? 'Cancelling…' : 'Cancel analysis'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ResultsPanel extends StatelessWidget {
  const _ResultsPanel({required this.viewModel});

  final AnalysisViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final result = viewModel.result!;
    final player = viewModel.selectedPlayer;

    return Card(
      key: const Key('analysis-results'),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Movement analysis results',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            if (result.courtCalibration case final calibration?) ...[
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.grid_on_outlined),
                title: Text(
                  'Standard doubles court: '
                  '${calibration.widthMeters?.toStringAsFixed(2)} m × '
                  '${calibration.lengthMeters?.toStringAsFixed(2)} m',
                ),
                subtitle: Text(
                  'Mapped from detected court lines • '
                  '${(calibration.confidence * 100).round()}% confidence'
                  '${result.inferenceDevice == null ? '' : ' • ${result.inferenceDevice}'}',
                ),
              ),
            ],
            if (result.players.isEmpty) ...[
              const SizedBox(height: 16),
              const ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(Icons.person_off_outlined),
                title: Text('No player track was found'),
                subtitle: Text(
                  'The analysis completed, but no track was long enough to report.',
                ),
              ),
            ] else ...[
              const SizedBox(height: 16),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.person_search_outlined),
                title: Text(viewModel.targetPlayer.label),
                subtitle: const Text('Selected athlete movement report'),
              ),
              const SizedBox(height: 16),
              _DirectionalMovement(player: player!),
              const SizedBox(height: 12),
              _TrackingCoverageCard(player: player, result: result),
              const SizedBox(height: 12),
              _MetricGrid(player: player),
              const SizedBox(height: 12),
              if (player.speed.unit != 'm/s')
                const ListTile(
                  leading: Icon(Icons.warning_amber_outlined),
                  title: Text('Metre-based charts unavailable'),
                  subtitle: Text(
                    'Court calibration or metric tracking validation failed. '
                    'Pixel curves are hidden. Recheck court lines and analyse again. '
                    'Tracking coverage does not indicate calibration accuracy.',
                  ),
                )
              else if (result.rawData['reportImages'] is List)
                _ReportImages(result: result)
              else ...[
                _SpeedSamplesChart(result: result),
                AccelerationChart(
                  key: const Key('acceleration-profile-chart'),
                  samples: player.acceleration.samples,
                  unit: player.acceleration.unit ?? 'unknown',
                ),
              ],
              if (player.deceleration.unit == 'm/s²')
                Text(
                  'Screened braking events: ${player.deceleration.events.length}. '
                  'Prototype threshold: −2 m/s² for at least 0.2 s; not a fatigue score.',
                ),
              const SizedBox(height: 12),
              const Text(
                'Overall effort / fatigue: awaiting client-defined calculation and validation.',
              ),
              const SizedBox(height: 12),
              ForceVelocityChart(analysis: player.forceVelocity),
            ],
            const SizedBox(height: 16),
            _ExportPanel(result: result),
            if (result.warnings.isNotEmpty) ...[
              const SizedBox(height: 16),
              _WarningsPanel(warnings: result.warnings),
            ],
            const SizedBox(height: 16),
            if (result.annotatedVideoUrl case final String url)
              _AnnotatedVideoCard(url: url)
            else
              const ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(Icons.ondemand_video_outlined),
                title: Text('Annotated video'),
                subtitle: Text('Not available for this analysis'),
              ),
          ],
        ),
      ),
    );
  }
}

class _TrackingCoverageCard extends StatelessWidget {
  const _TrackingCoverageCard({required this.player, required this.result});

  final PlayerAnalysis player;
  final AnalysisResult result;

  @override
  Widget build(BuildContext context) {
    final trackedFrames =
        player.trackedFrames ?? player.movementPath.points.length;
    final processedFrames =
        result.processedFrames ?? result.inputVideo?.frameCount;
    final coverage = processedFrames != null && processedFrames > 0
        ? (trackedFrames / processedFrames).clamp(0.0, 1.0)
        : null;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.track_changes_outlined),
                const SizedBox(width: 12),
                Text(
                  'Tracking coverage',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (coverage != null) LinearProgressIndicator(value: coverage),
            const SizedBox(height: 8),
            Text(
              processedFrames == null
                  ? '$trackedFrames tracked frames'
                  : '$trackedFrames of $processedFrames frames • '
                        '${((coverage ?? 0) * 100).round()}%',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 4),
            Text(
              'This shows how much of the processed video contained a usable '
              'position for the selected athlete.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (player.metricDurationSeconds case final double seconds) ...[
              const SizedBox(height: 8),
              Text(
                'Metric calculation covers ${seconds.toStringAsFixed(2)} s of screened intervals. '
                '${player.excludedMetricSamples ?? 0} candidate samples excluded. '
                'Distances exclude gaps and filter edges; they are not a full-session total.',
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _MetricGrid extends StatelessWidget {
  const _MetricGrid({required this.player});

  final PlayerAnalysis player;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final cardWidth = constraints.maxWidth >= 620
            ? (constraints.maxWidth - 12) / 2
            : constraints.maxWidth;

        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Total distance',
                value: _formatMetric(
                  player.totalDistance.value,
                  player.totalDistance.unit,
                ),
                icon: Icons.route_outlined,
                note: player.totalDistance.note,
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Speed',
                value: _formatSpeed(player.speed),
                icon: Icons.speed_outlined,
                note: player.speed.note,
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Direction changes',
                value: player.directionChanges.count?.toString() ?? '—',
                icon: Icons.turn_sharp_right_outlined,
                note: player.directionChanges.note,
              ),
            ),
          ],
        );
      },
    );
  }

  static String _formatMetric(double? value, String? unit) {
    if (value == null) return '—';
    final formatted = value.abs() >= 100
        ? value.toStringAsFixed(0)
        : value.toStringAsFixed(1);
    return unit == null ? formatted : '$formatted $unit';
  }

  static String _formatSpeed(SpeedMetric speed) {
    if (speed.average == null) return '—';
    final average = _formatMetric(speed.average, speed.unit);
    if (speed.peak == null) return 'Average $average';
    return 'Avg $average • Peak ${_formatMetric(speed.peak, speed.unit)}';
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    required this.icon,
    this.note,
  });

  final String label;
  final String value;
  final IconData icon;
  final String? note;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label),
                  const SizedBox(height: 4),
                  Text(value, style: Theme.of(context).textTheme.titleMedium),
                  if (note != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      note!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WarningsPanel extends StatelessWidget {
  const _WarningsPanel({required this.warnings});

  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.tertiaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Analysis notes',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 4),
                  for (final warning in warnings) Text('• $warning'),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AnnotatedVideoCard extends StatefulWidget {
  const _AnnotatedVideoCard({required this.url});

  final String url;

  @override
  State<_AnnotatedVideoCard> createState() => _AnnotatedVideoCardState();
}

class _AnnotatedVideoCardState extends State<_AnnotatedVideoCard> {
  late final VideoPlayerController _controller;
  Object? _loadError;

  @override
  void initState() {
    super.initState();
    _controller = VideoPlayerController.networkUrl(
      Uri.parse(widget.url),
      httpHeaders: {
        if (AuthRepository.token != null)
          'Authorization': 'Bearer ${AuthRepository.token}',
      },
    );
    _controller
        .initialize()
        .then((_) {
          if (mounted) setState(() {});
        })
        .catchError((Object error) {
          if (mounted) setState(() => _loadError = error);
        });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loadError != null) {
      return const ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(Icons.video_file_outlined),
        title: Text('Annotated video created'),
        subtitle: Text(
          'The preview could not be loaded from the local service.',
        ),
      );
    }
    if (!_controller.value.isInitialized) {
      return const ListTile(
        contentPadding: EdgeInsets.zero,
        leading: SizedBox.square(
          dimension: 22,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        title: Text('Loading annotated video…'),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Annotated video', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            onTap: _openFullscreen,
            child: AspectRatio(
              aspectRatio: _controller.value.aspectRatio,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  VideoPlayer(_controller),
                  const Align(
                    alignment: Alignment.topRight,
                    child: Padding(
                      padding: EdgeInsets.all(8),
                      child: Icon(
                        Icons.fullscreen,
                        color: Colors.white,
                        shadows: [Shadow(blurRadius: 4)],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        VideoProgressIndicator(_controller, allowScrubbing: true),
        Row(
          children: [
            IconButton.filledTonal(
              tooltip: _controller.value.isPlaying ? 'Pause' : 'Play',
              onPressed: _togglePlayback,
              icon: Icon(
                _controller.value.isPlaying ? Icons.pause : Icons.play_arrow,
              ),
            ),
            const SizedBox(width: 8),
            TextButton.icon(
              key: const Key('expand-annotated-video-button'),
              onPressed: _openFullscreen,
              icon: const Icon(Icons.fullscreen),
              label: const Text('View full screen'),
            ),
          ],
        ),
      ],
    );
  }

  void _togglePlayback() {
    setState(() {
      if (_controller.value.isPlaying) {
        _controller.pause();
      } else {
        _controller.play();
      }
    });
  }

  Future<void> _openFullscreen() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (context) => _FullScreenVideoPage(controller: _controller),
      ),
    );
    if (mounted) setState(() {});
  }
}

class _FullScreenVideoPage extends StatefulWidget {
  const _FullScreenVideoPage({required this.controller});

  final VideoPlayerController controller;

  @override
  State<_FullScreenVideoPage> createState() => _FullScreenVideoPageState();
}

class _FullScreenVideoPageState extends State<_FullScreenVideoPage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Annotated video'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: Center(
                child: InteractiveViewer(
                  minScale: 1,
                  maxScale: 4,
                  child: AspectRatio(
                    aspectRatio: widget.controller.value.aspectRatio,
                    child: VideoPlayer(widget.controller),
                  ),
                ),
              ),
            ),
            VideoProgressIndicator(
              widget.controller,
              allowScrubbing: true,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            ),
            IconButton.filled(
              tooltip: widget.controller.value.isPlaying ? 'Pause' : 'Play',
              onPressed: () {
                setState(() {
                  if (widget.controller.value.isPlaying) {
                    widget.controller.pause();
                  } else {
                    widget.controller.play();
                  }
                });
              },
              icon: Icon(
                widget.controller.value.isPlaying
                    ? Icons.pause
                    : Icons.play_arrow,
              ),
            ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: ListTile(
        leading: Icon(
          Icons.error_outline,
          color: Theme.of(context).colorScheme.onErrorContainer,
        ),
        title: const Text('Analysis failed'),
        subtitle: Text(message),
        trailing: TextButton(onPressed: onRetry, child: const Text('Retry')),
      ),
    );
  }
}

class _DirectionalMovement extends StatelessWidget {
  const _DirectionalMovement({required this.player});
  final PlayerAnalysis player;
  @override
  Widget build(BuildContext context) {
    final metres = player.movementPath.coordinateSystem.contains('court');
    final entries = [
      (
        metres ? 'Lateral movement' : 'Horizontal image movement',
        player.leftRightDistance,
      ),
      (
        metres ? 'Forward/back movement' : 'Vertical image movement',
        player.forwardBackDistance,
      ),
    ];
    final largest = math.max(
      player.leftRightDistance.value ?? 0,
      player.forwardBackDistance.value ?? 0,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Directional movement',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            for (final entry in entries) ...[
              Row(
                children: [
                  Expanded(child: Text(entry.$1)),
                  Text(
                    _MetricGrid._formatMetric(entry.$2.value, entry.$2.unit),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              LinearProgressIndicator(
                value: largest > 0
                    ? ((entry.$2.value ?? 0) / largest).clamp(0, 1)
                    : 0,
              ),
              const SizedBox(height: 12),
            ],
            Text(
              metres
                  ? 'Accumulated court-axis distances; diagonal movement contributes to both axes. Their sum is not total distance.'
                  : 'Pixel demonstration mode. Horizontal/vertical image movement is not real-world court left-right/forward-back distance.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _SpeedSamplesChart extends StatelessWidget {
  const _SpeedSamplesChart({required this.result});
  final AnalysisResult result;
  @override
  Widget build(BuildContext context) {
    final player = result.playerById(result.selectedTrackId);
    return AccelerationChart(
      key: const Key('speed-profile-chart'),
      title: 'Speed over time',
      unit: player?.speed.unit ?? 'unknown',
      samples: player?.speed.samples ?? const [],
    );
  }
}

class _ExportPanel extends StatefulWidget {
  const _ExportPanel({required this.result});
  final AnalysisResult result;
  @override
  State<_ExportPanel> createState() => _ExportPanelState();
}

class _ReportImages extends StatelessWidget {
  const _ReportImages({required this.result});
  final AnalysisResult result;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Text(
        'Metric reports — tap to enlarge. Tracking gaps are not joined. '
        'Shaded bands indicate braking events, not measured fatigue.',
      ),
      for (final item in (result.rawData['reportImages'] as List))
        Card(
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Column(
              children: [
                Text(item['title'] as String),
                InkWell(
                  onTap: () => showDialog<void>(
                    context: context,
                    builder: (context) => Dialog.fullscreen(
                      child: Scaffold(
                        appBar: AppBar(title: Text(item['title'] as String)),
                        body: InteractiveViewer(
                          maxScale: 8,
                          child: Center(child: _image(item['url'] as String)),
                        ),
                      ),
                    ),
                  ),
                  child: _image(item['url'] as String),
                ),
              ],
            ),
          ),
        ),
    ],
  );

  Widget _image(String url) => Image.network(
    url,
    headers: {
      if (AuthRepository.token != null)
        'Authorization': 'Bearer ${AuthRepository.token}',
    },
    errorBuilder: (_, error, stack) => const Padding(
      padding: EdgeInsets.all(16),
      child: Text(
        'Report image could not be loaded. Check your connection or sign in again.',
      ),
    ),
  );
}

class _ExportPanelState extends State<_ExportPanel> {
  bool _busy = false;
  String? _message;
  final _service = AnalysisExportService();
  Future<void> _save(Future<String?> Function() action) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final path = await action();
      if (mounted) {
        setState(
          () => _message = path == null
              ? 'Export cancelled.'
              : 'Export saved successfully.',
        );
      }
    } catch (error) {
      if (mounted) {
        setState(() => _message = 'Export failed. Please try again. $error');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('Export results', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          OutlinedButton.icon(
            key: const Key('export-csv-button'),
            onPressed: _busy
                ? null
                : () =>
                      _save(() => _service.saveData(widget.result, csv: true)),
            icon: const Icon(Icons.table_chart_outlined),
            label: const Text('Export CSV'),
          ),
          OutlinedButton.icon(
            key: const Key('export-json-button'),
            onPressed: _busy
                ? null
                : () =>
                      _save(() => _service.saveData(widget.result, csv: false)),
            icon: const Icon(Icons.data_object),
            label: const Text('Export JSON'),
          ),
          OutlinedButton.icon(
            key: const Key('export-video-button'),
            onPressed: _busy || widget.result.annotatedVideoUrl == null
                ? null
                : () => _save(() => _service.saveVideo(widget.result)),
            icon: const Icon(Icons.download_outlined),
            label: const Text('Save annotated video'),
          ),
          if (widget.result.rawData['reportArchiveUrl'] is String)
            OutlinedButton.icon(
              key: const Key('export-reports-button'),
              onPressed: _busy
                  ? null
                  : () => _save(() => _service.saveReports(widget.result)),
              icon: const Icon(Icons.folder_zip_outlined),
              label: const Text('Save report images + data'),
            ),
        ],
      ),
      if (_busy) const LinearProgressIndicator(),
      if (_message != null) Text(_message!),
    ],
  );
}
