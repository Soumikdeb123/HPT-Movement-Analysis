import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../auth/repositories/auth_repository.dart';
import '../models/analysis_result.dart';

class SprintEventsPage extends StatefulWidget {
  const SprintEventsPage({
    super.key,
    required this.videoUrl,
    required this.events,
    this.recommendedEventIds = const [],
  });

  final String videoUrl;
  final List<ForceVelocityEvent> events;
  final List<String> recommendedEventIds;

  @override
  State<SprintEventsPage> createState() => _SprintEventsPageState();
}

class _SprintEventsPageState extends State<SprintEventsPage> {
  late final VideoPlayerController _controller;
  late final List<ForceVelocityEvent> _events;
  Object? _error;
  String? _activeId;
  int _playGeneration = 0;

  @override
  void initState() {
    super.initState();
    _events = [...widget.events]
      ..sort((a, b) => a.startTimeSeconds.compareTo(b.startTimeSeconds));
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
    _playGeneration++;
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sprint events')),
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
                  return Card(
                    color: selected
                        ? Theme.of(context).colorScheme.primaryContainer
                        : null,
                    child: ListTile(
                      key: Key('sprint-event-${index + 1}'),
                      leading: CircleAvatar(child: Text('${index + 1}')),
                      title: Text(
                        'Event ${index + 1} · ${_time(event.startTimeSeconds)}',
                      ),
                      subtitle: Text(
                        '${event.durationSeconds.toStringAsFixed(1)} s · '
                        '${event.startSpeedMps.toStringAsFixed(1)} → '
                        '${event.peakSpeedMps.toStringAsFixed(1)} m/s · '
                        '${event.meanForceNPerKg.toStringAsFixed(2)} N/kg'
                        '${recommended ? '\nRecommended for review' : ''}',
                      ),
                      isThreeLine: recommended,
                      trailing: const Icon(Icons.play_arrow),
                      onTap: () => _playEvent(event),
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
    return index < 0 ? null : 'Viewing event ${index + 1}';
  }

  void _toggle() {
    if (!_controller.value.isInitialized) return;
    setState(() {
      if (_controller.value.isPlaying) {
        _playGeneration++;
        _controller.pause();
      } else {
        _activeId = null;
        _controller.play();
      }
    });
  }

  Future<void> _playEvent(ForceVelocityEvent event) async {
    if (!_controller.value.isInitialized) return;
    final generation = ++_playGeneration;
    setState(() => _activeId = event.id);
    await _controller.seekTo(
      Duration(milliseconds: (event.seekStartSeconds * 1000).round()),
    );
    await _controller.play();
    if (mounted) setState(() {});
    final seconds = math.max(.5, event.seekEndSeconds - event.seekStartSeconds);
    await Future<void>.delayed(
      Duration(milliseconds: (seconds * 1000).round()),
    );
    if (!mounted || generation != _playGeneration) return;
    await _controller.pause();
    if (mounted) setState(() {});
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
