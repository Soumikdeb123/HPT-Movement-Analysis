import 'package:flutter/material.dart';

import '../models/player_profile.dart';

class PlayerSelectorCard extends StatelessWidget {
  const PlayerSelectorCard({
    super.key,
    required this.players,
    required this.selected,
    required this.loading,
    required this.onSelect,
    required this.onAdd,
    required this.onRefresh,
    this.error,
  });

  final List<PlayerProfile> players;
  final PlayerProfile? selected;
  final bool loading;
  final String? error;
  final ValueChanged<PlayerProfile> onSelect;
  final VoidCallback onAdd;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('1. Player', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          const Text(
            'Who is this analysis for? Every result and report will be saved to this player.',
          ),
          const SizedBox(height: 16),
          if (loading) const LinearProgressIndicator(),
          if (error != null) ...[
            Text(
              error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            TextButton.icon(
              onPressed: onRefresh,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ],
          if (!loading && players.isEmpty && error == null)
            const Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: Text('Create the first player before selecting a video.'),
            ),
          if (players.isNotEmpty)
            DropdownButtonFormField<String>(
              key: const Key('player-selector'),
              initialValue: selected?.id,
              decoration: const InputDecoration(
                labelText: 'Player',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.person_outline),
              ),
              items: [
                for (final player in players)
                  DropdownMenuItem(
                    value: player.id,
                    child: Text(
                      '${player.name} · ${player.analysisCount} '
                      '${player.analysisCount == 1 ? 'analysis' : 'analyses'}',
                    ),
                  ),
              ],
              onChanged: (id) {
                if (id == null) return;
                onSelect(players.firstWhere((player) => player.id == id));
              },
            ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            key: const Key('add-player-button'),
            onPressed: onAdd,
            icon: const Icon(Icons.person_add_alt_1_outlined),
            label: const Text('Add player'),
          ),
        ],
      ),
    ),
  );
}

Future<MapEntry<String, double?>?> showCreatePlayerDialog(
  BuildContext context,
) async {
  final name = TextEditingController();
  final mass = TextEditingController();
  return showDialog<MapEntry<String, double?>>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Add player'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const Key('new-player-name'),
            controller: name,
            autofocus: true,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
              labelText: 'Player name',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: mass,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Default body mass (optional)',
              suffixText: 'kg',
              border: OutlineInputBorder(),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            final cleanName = name.text.trim();
            final parsedMass = mass.text.trim().isEmpty
                ? null
                : double.tryParse(mass.text.trim());
            if (cleanName.isEmpty ||
                (mass.text.trim().isNotEmpty && parsedMass == null)) {
              return;
            }
            Navigator.pop(dialogContext, MapEntry(cleanName, parsedMass));
          },
          child: const Text('Create player'),
        ),
      ],
    ),
  );
}
