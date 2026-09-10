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
                        const SizedBox(height: 16),
                        _TargetPlayerCard(viewModel: viewModel),
                        const SizedBox(height: 16),
                        const _ScopeCard(),
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

class _ScopeCard extends StatelessWidget {
  const _ScopeCard();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '3. Review prototype scope',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            const ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.science_outlined),
              title: Text('Experimental court calibration'),
              subtitle: Text(
                'Court lines are detected and mapped to standard tennis-court '
                'dimensions. Results are estimates until manually validated.',
              ),
            ),
            const ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.person_search_outlined),
              title: Text('One selected athlete'),
              subtitle: Text(
                'The detector can see both players, but the report contains only '
                'the court-side athlete selected before processing.',
              ),
            ),
          ],
        ),
      ),
    );
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
              '2. Select the athlete',
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
          ],
        ),
      ),
    );
  }
}

class _ProgressPanel extends StatelessWidget {
  const _ProgressPanel({
    required this.progress,
    required this.isCancelling,
    required this.onCancel,
  });

  final double progress;
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
              const Text(
                'Keep this screen open. Local processing may take several minutes.',
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
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Prototype results',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                _ResultStatusChip(
                  status: MetricStatus.experimental,
                  text: result.courtCalibration == null
                      ? 'Uncalibrated'
                      : 'Estimated court mapping',
                ),
              ],
            ),
            if (result.courtCalibration case final calibration?) ...[
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.grid_on_outlined),
                title: Text(
                  'Court mapped to ${calibration.widthMeters?.toStringAsFixed(2)} m '
                  '× ${calibration.lengthMeters?.toStringAsFixed(2)} m',
                ),
                subtitle: Text(
                  'Automatic line detection • ${(calibration.confidence * 100).round()}% '
                  'detector confidence${result.inferenceDevice == null ? '' : ' • ${result.inferenceDevice}'}',
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
              _MovementPathCard(path: player.movementPath),
              const SizedBox(height: 12),
              _MetricGrid(player: player),
              const SizedBox(height: 12),
              _SpeedSamplesChart(result: result),
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

class _MovementPathCard extends StatelessWidget {
  const _MovementPathCard({required this.path});

  final MovementPath path;

  @override
  Widget build(BuildContext context) {
    final hasPath = path.points.length >= 2;
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
                const Icon(Icons.timeline_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Movement path',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                _ResultStatusChip(status: path.status),
              ],
            ),
            const SizedBox(height: 12),
            if (hasPath)
              SizedBox(
                height: 220,
                child: CustomPaint(
                  key: const Key('movement-path-chart'),
                  painter: _TrajectoryPainter(
                    points: path.points,
                    colour: Theme.of(context).colorScheme.primary,
                    gridColour: Theme.of(context).colorScheme.outlineVariant,
                  ),
                  child: const SizedBox.expand(),
                ),
              )
            else
              const SizedBox(
                height: 96,
                child: Center(child: Text('No movement path available')),
              ),
            const SizedBox(height: 8),
            Text(
              hasPath
                  ? '${path.points.length} tracked positions • '
                        '${path.coordinateSystem == 'estimated_court_metres' ? 'Estimated court coordinates' : 'Image coordinates'}'
                  : path.note ??
                        'The current track has insufficient positions.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
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
                status: player.totalDistance.status,
                note: player.totalDistance.note,
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Speed',
                value: _formatSpeed(player.speed),
                icon: Icons.speed_outlined,
                status: player.speed.status,
                note: player.speed.note,
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Acceleration',
                value: _formatMetric(
                  player.acceleration.value,
                  player.acceleration.unit,
                ),
                icon: Icons.trending_up,
                status: player.acceleration.status,
                note: player.acceleration.note,
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Deceleration',
                value: _formatMetric(
                  player.deceleration.value,
                  player.deceleration.unit,
                ),
                icon: Icons.trending_down,
                status: player.deceleration.status,
                note: player.deceleration.note,
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Overall effort load',
                value: _formatMetric(
                  player.overallEffort.value,
                  player.overallEffort.unit,
                ),
                icon: Icons.monitor_heart_outlined,
                status: player.overallEffort.status,
                note:
                    player.overallEffort.note ??
                    'Effort formula awaiting client validation.',
              ),
            ),
            SizedBox(
              width: cardWidth,
              child: _MetricTile(
                label: 'Direction changes',
                value: player.directionChanges.count?.toString() ?? '—',
                icon: Icons.turn_sharp_right_outlined,
                status: player.directionChanges.status,
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
    required this.status,
    this.note,
  });

  final String label;
  final String value;
  final IconData icon;
  final MetricStatus status;
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
                  Row(
                    children: [
                      Expanded(child: Text(label)),
                      _ResultStatusChip(status: status),
                    ],
                  ),
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

class _ResultStatusChip extends StatelessWidget {
  const _ResultStatusChip({required this.status, this.text});

  final MetricStatus status;
  final String? text;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final (background, foreground) = switch (status) {
      MetricStatus.calibrated => (
        colorScheme.primaryContainer,
        colorScheme.onPrimaryContainer,
      ),
      MetricStatus.experimental => (
        colorScheme.tertiaryContainer,
        colorScheme.onTertiaryContainer,
      ),
      MetricStatus.unavailable => (
        colorScheme.surfaceContainerLow,
        colorScheme.onSurfaceVariant,
      ),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text ?? status.label,
        style: Theme.of(context).textTheme.labelSmall
            ?.copyWith(color: foreground),
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
                    'Prototype limitations',
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

class _TrajectoryPainter extends CustomPainter {
  const _TrajectoryPainter({
    required this.points,
    required this.colour,
    required this.gridColour,
    this.flipY = false,
  });

  final List<TrajectoryPoint> points;
  final Color colour;
  final Color gridColour;
  final bool flipY;

  @override
  void paint(Canvas canvas, Size size) {
    const padding = 12.0;
    final drawingRect = Rect.fromLTWH(
      padding,
      padding,
      math.max(1, size.width - padding * 2),
      math.max(1, size.height - padding * 2),
    );
    final gridPaint = Paint()
      ..color = gridColour
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    canvas.drawRect(drawingRect, gridPaint);
    for (var index = 1; index < 4; index += 1) {
      final fraction = index / 4;
      canvas.drawLine(
        Offset(
          drawingRect.left + drawingRect.width * fraction,
          drawingRect.top,
        ),
        Offset(
          drawingRect.left + drawingRect.width * fraction,
          drawingRect.bottom,
        ),
        gridPaint,
      );
      canvas.drawLine(
        Offset(
          drawingRect.left,
          drawingRect.top + drawingRect.height * fraction,
        ),
        Offset(
          drawingRect.right,
          drawingRect.top + drawingRect.height * fraction,
        ),
        gridPaint,
      );
    }

    final minimumX = points.map((point) => point.x).reduce(math.min);
    final maximumX = points.map((point) => point.x).reduce(math.max);
    final minimumY = points.map((point) => point.y).reduce(math.min);
    final maximumY = points.map((point) => point.y).reduce(math.max);
    final xRange = math.max(1.0, maximumX - minimumX);
    final yRange = math.max(1.0, maximumY - minimumY);

    Offset scale(TrajectoryPoint point) {
      return Offset(
        drawingRect.left + ((point.x - minimumX) / xRange) * drawingRect.width,
        drawingRect.top +
            (flipY
                    ? 1 - (point.y - minimumY) / yRange
                    : (point.y - minimumY) / yRange) *
                drawingRect.height,
      );
    }

    final firstOffset = scale(points.first);
    final path = Path()..moveTo(firstOffset.dx, firstOffset.dy);
    for (final point in points.skip(1)) {
      final offset = scale(point);
      path.lineTo(offset.dx, offset.dy);
    }
    final trajectoryPaint = Paint()
      ..color = colour
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(path, trajectoryPaint);

    final markerPaint = Paint()..color = colour;
    canvas.drawCircle(firstOffset, 5, markerPaint);
    canvas.drawCircle(scale(points.last), 7, markerPaint);
  }

  @override
  bool shouldRepaint(covariant _TrajectoryPainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.colour != colour ||
        oldDelegate.gridColour != gridColour;
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
        metres ? 'Left-right movement' : 'Horizontal image movement',
        player.leftRightDistance,
      ),
      (
        metres ? 'Forward-back movement' : 'Vertical image movement',
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
                  : 'Court mapping is unavailable. Image-axis movement cannot yet represent court left-right or forward-back distance.',
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
    final players = result.rawData['players'];
    if (players is! List || players.isEmpty) return const SizedBox.shrink();
    final speed = (players.first as Map)['speed'];
    if (speed is! Map || speed['samples'] is! List) {
      return const SizedBox.shrink();
    }
    final samples = (speed['samples'] as List)
        .whereType<Map>()
        .where((s) => s['timeSeconds'] is num && s['value'] is num)
        .toList();
    if (samples.length < 2) return const SizedBox.shrink();
    final points = samples
        .map(
          (s) => TrajectoryPoint(
            timeSeconds: (s['timeSeconds'] as num).toDouble(),
            x: (s['timeSeconds'] as num).toDouble(),
            y: (s['value'] as num).toDouble(),
          ),
        )
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Speed profile (${speed['unit'] ?? ''})',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        SizedBox(
          height: 160,
          child: CustomPaint(
            key: const Key('speed-profile-chart'),
            painter: _TrajectoryPainter(
              points: points,
              flipY: true,
              colour: Theme.of(context).colorScheme.primary,
              gridColour: Theme.of(context).colorScheme.outlineVariant,
            ),
            child: const SizedBox.expand(),
          ),
        ),
        Text(
          'Elapsed time: ${points.first.x.toStringAsFixed(1)}–${points.last.x.toStringAsFixed(1)} s. '
          'Speed increases upward. Export JSON for every time-stamped sample.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

class _ExportPanel extends StatefulWidget {
  const _ExportPanel({required this.result});
  final AnalysisResult result;
  @override
  State<_ExportPanel> createState() => _ExportPanelState();
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
        ],
      ),
      if (_busy) const LinearProgressIndicator(),
      if (_message != null) Text(_message!),
    ],
  );
}
