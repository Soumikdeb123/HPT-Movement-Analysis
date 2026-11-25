import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../auth/repositories/auth_repository.dart';
import '../models/analysis_result.dart';

class MovementMomentsPage extends StatefulWidget {
  const MovementMomentsPage({
    super.key,
    required this.videoUrl,
    required this.events,
    this.recommendedEventIds = const [],
    this.onSetExcluded,
  });

  final String videoUrl;
  final List<ForceVelocityEvent> events;
  final List<String> recommendedEventIds;
  final Future<void> Function(String eventId, bool excluded)? onSetExcluded;

  @override
  State<MovementMomentsPage> createState() => _MovementMomentsPageState();
}

class _MovementMomentsPageState extends State<MovementMomentsPage> {
  late final VideoPlayerController _controller;
  late final List<ForceVelocityEvent> _events;
  Object? _error;
  String? _activeId;
  late final Set<String> _excludedIds;
  String? _updatingId;

  @override
  void initState() {
    super.initState();
    _events = [...widget.events]
      ..sort((a, b) => a.startTimeSeconds.compareTo(b.startTimeSeconds));
    _excludedIds = {
      for (final event in _events)
        if (event.excluded) event.id,
    };
    _controller = VideoPlayerController.networkUrl(
      Uri.parse(widget.videoUrl),
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
          if (mounted) setState(() => _error = error);
        });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Key movement moments')),
      body: SafeArea(
        child: Column(
          children: [
            _VideoPanel(
              controller: _controller,
              error: _error,
              activeLabel: _activeLabel,
              onToggle: _toggle,
            ),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                itemCount: _events.length,
                separatorBuilder: (_, _) => const SizedBox(height: 8),
                itemBuilder: (context, index) {
                  final event = _events[index];
                  final selected = event.id == _activeId;
                  final recommended = widget.recommendedEventIds.contains(
                    event.id,
                  );
                  final excluded = _excludedIds.contains(event.id);
                  return Card(
                    color: selected
                        ? Theme.of(context).colorScheme.primaryContainer
                        : null,
                    child: Column(
                      children: [
                        ListTile(
                          key: Key('movement-moment-${index + 1}'),
                          leading: CircleAvatar(child: Text('${index + 1}')),
                          title: Text(
                            '${event.label} · ${_time(event.startTimeSeconds)}',
                          ),
                          subtitle: Text(
                            '${event.startSpeedMps.toStringAsFixed(1)} → '
                            '${event.peakSpeedMps.toStringAsFixed(1)} m/s'
                            '${recommended ? '\nRecommended for review' : ''}'
                            '${excluded ? '\nExcluded from this analysis' : ''}',
                          ),
                          isThreeLine: recommended || excluded,
                          trailing: const Icon(Icons.play_arrow),
                          onTap: () => _playEvent(event),
                        ),
                        if (widget.onSetExcluded != null)
                          Align(
                            alignment: Alignment.centerRight,
                            child: TextButton.icon(
                              key: Key('exclude-movement-moment-${index + 1}'),
                              onPressed: _updatingId == null
                                  ? () => _setExcluded(event, !excluded)
                                  : null,
                              icon: _updatingId == event.id
                                  ? const SizedBox.square(
                                      dimension: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : Icon(
                                      excluded
                                          ? Icons.undo
                                          : Icons.remove_circle_outline,
                                    ),
                              label: Text(
                                excluded
                                    ? 'Undo exclusion'
                                    : 'Exclude from this analysis',
                              ),
                            ),
                          ),
                      ],
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  String? get _activeLabel {
    final index = _events.indexWhere((event) => event.id == _activeId);
    return index < 0 ? null : 'Playing movement moment ${index + 1}';
  }

  void _toggle() {
    if (!_controller.value.isInitialized) return;
    setState(() {
      if (_controller.value.isPlaying) {
        _controller.pause();
      } else {
        _activeId = null;
        _controller.play();
      }
    });
  }

  Future<void> _playEvent(ForceVelocityEvent event) async {
    if (!_controller.value.isInitialized) return;
    setState(() => _activeId = event.id);
    await _controller.seekTo(
      Duration(milliseconds: (event.seekStartSeconds * 1000).round()),
    );
    await _controller.play();
    if (mounted) setState(() {});
  }

  Future<void> _setExcluded(ForceVelocityEvent event, bool excluded) async {
    final callback = widget.onSetExcluded;
    if (callback == null) return;
    setState(() => _updatingId = event.id);
    try {
      await callback(event.id, excluded);
      if (!mounted) return;
      setState(() {
        if (excluded) {
          _excludedIds.add(event.id);
        } else {
          _excludedIds.remove(event.id);
        }
      });
    } on Object catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not update the curve. $error')),
      );
    } finally {
      if (mounted) setState(() => _updatingId = null);
    }
  }

  static String _time(double seconds) {
    final minutes = seconds ~/ 60;
    final remainder = seconds - minutes * 60;
    return '$minutes:${remainder.toStringAsFixed(1).padLeft(4, '0')}';
  }
}

class _VideoPanel extends StatelessWidget {
  const _VideoPanel({
    required this.controller,
    required this.error,
    required this.activeLabel,
    required this.onToggle,
  });

  final VideoPlayerController controller;
  final Object? error;
  final String? activeLabel;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    if (error != null) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Text('The annotated video could not be loaded.'),
      );
    }
    if (!controller.value.isInitialized) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: CircularProgressIndicator(),
      );
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (activeLabel != null) ...[
            Text(activeLabel!, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
          ],
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: AspectRatio(
              aspectRatio: controller.value.aspectRatio,
              child: VideoPlayer(controller),
            ),
          ),
          VideoProgressIndicator(
            controller,
            allowScrubbing: true,
            padding: const EdgeInsets.symmetric(vertical: 8),
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: IconButton.filledTonal(
              onPressed: onToggle,
              icon: Icon(
                controller.value.isPlaying ? Icons.pause : Icons.play_arrow,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
