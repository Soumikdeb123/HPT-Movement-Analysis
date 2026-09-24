import 'package:flutter/material.dart';

class PrivacyConsentGate extends StatefulWidget {
  const PrivacyConsentGate({required this.child, super.key});

  final Widget child;

  @override
  State<PrivacyConsentGate> createState() => _PrivacyConsentGateState();
}

class _PrivacyConsentGateState extends State<PrivacyConsentGate> {
  var _accessGranted = false;

  @override
  Widget build(BuildContext context) {
    if (_accessGranted) {
      return widget.child;
    }

    return _PrivacyConsentPage(
      onContinue: () => setState(() => _accessGranted = true),
    );
  }
}

class _PrivacyConsentPage extends StatefulWidget {
  const _PrivacyConsentPage({required this.onContinue});

  final VoidCallback onContinue;

  @override
  State<_PrivacyConsentPage> createState() => _PrivacyConsentPageState();
}

class _PrivacyConsentPageState extends State<_PrivacyConsentPage> {
  var _showUnder18Requirements = false;
  var _guardianPermissionConfirmed = false;
  var _organisationPermissionConfirmed = false;
  var _noticeRead = false;

  bool get _canContinueAsMinor =>
      _guardianPermissionConfirmed &&
      _organisationPermissionConfirmed &&
      _noticeRead;

  @override
  Widget build(BuildContext context) {
    final colourScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Privacy and participation')),
      body: SafeArea(
        child: ListView(
          key: const Key('privacy-consent-screen'),
          padding: const EdgeInsets.all(20),
          children: [
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Icon(
                      Icons.privacy_tip_outlined,
                      size: 52,
                      color: colourScheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Before you use HPT Player Analysis',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'This prototype is designed to analyse player movement '
                      'and workload. It does not analyse ball landing '
                      'positions.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 20),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: const [
                            _NoticeSection(
                              title: 'Data covered',
                              body:
                                  'Video footage and derived player metrics, '
                                  'including left-right and forward-back '
                                  'movement, distance, speed, acceleration, '
                                  'deceleration, direction changes and overall '
                                  'effort.',
                            ),
                            _NoticeSection(
                              title: 'Purpose and access',
                              body:
                                  'The data may be used only for authorised '
                                  'movement and workload analysis, project '
                                  'testing and agreed coaching review. Access '
                                  'must be limited to authorised project and '
                                  'coaching personnel, with no unrelated '
                                  'sharing or reuse.',
                            ),
                            _NoticeSection(
                              title: 'Handling requirements',
                              body:
                                  'Obtain permission before recording or '
                                  'processing; use secure storage; define how '
                                  'long files and results will be retained; '
                                  'delete them when no longer required; and '
                                  'provide a way to withdraw permission or '
                                  'request deletion.',
                            ),
                            _NoticeSection(
                              title: 'Processing and consent',
                              body:
                                  'Selected videos are uploaded to the configured '
                                  'analysis server for player tracking. '
                                  'This screen uses a session-only '
                                  'acknowledgement and does not replace '
                                  'written consent or organisational approval.',
                              isLast: true,
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Card(
                      color: colourScheme.primaryContainer,
                      child: CheckboxListTile(
                        key: const Key('adult-confirmation-checkbox'),
                        value: false,
                        onChanged: (value) {
                          if (value == true) {
                            widget.onContinue();
                          }
                        },
                        controlAffinity: ListTileControlAffinity.leading,
                        title: const Text("I'm 18 years old or over"),
                        subtitle: const Text(
                          'Confirm this to continue to the application now.',
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      key: const Key('under-18-button'),
                      onPressed: () =>
                          setState(() => _showUnder18Requirements = true),
                      icon: const Icon(Icons.family_restroom_outlined),
                      label: const Text('I am under 18 years old'),
                    ),
                    if (_showUnder18Requirements) ...[
                      const SizedBox(height: 16),
                      Card(
                        key: const Key('minor-requirements-panel'),
                        color: colourScheme.tertiaryContainer,
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                'Requirements for an athlete under 18',
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                              const SizedBox(height: 8),
                              const Text(
                                'Do not upload or process footage unless a '
                                'parent or legal guardian has given informed '
                                'written permission and the responsible coach '
                                'or organisation has approved the intended '
                                'recording, access, storage, retention and '
                                'deletion arrangements.',
                              ),
                              const SizedBox(height: 8),
                              CheckboxListTile(
                                key: const Key('guardian-consent-checkbox'),
                                contentPadding: EdgeInsets.zero,
                                controlAffinity:
                                    ListTileControlAffinity.leading,
                                value: _guardianPermissionConfirmed,
                                onChanged: (value) => setState(
                                  () => _guardianPermissionConfirmed =
                                      value ?? false,
                                ),
                                title: const Text(
                                  'A parent or legal guardian has given '
                                  'informed written permission.',
                                ),
                              ),
                              CheckboxListTile(
                                key: const Key(
                                  'organisation-permission-checkbox',
                                ),
                                contentPadding: EdgeInsets.zero,
                                controlAffinity:
                                    ListTileControlAffinity.leading,
                                value: _organisationPermissionConfirmed,
                                onChanged: (value) => setState(
                                  () => _organisationPermissionConfirmed =
                                      value ?? false,
                                ),
                                title: const Text(
                                  'The responsible coach or organisation has '
                                  'approved this footage and its stated use.',
                                ),
                              ),
                              CheckboxListTile(
                                key: const Key('privacy-notice-read-checkbox'),
                                contentPadding: EdgeInsets.zero,
                                controlAffinity:
                                    ListTileControlAffinity.leading,
                                value: _noticeRead,
                                onChanged: (value) => setState(
                                  () => _noticeRead = value ?? false,
                                ),
                                title: const Text(
                                  'I have read and understood the privacy and '
                                  'data-processing notice above.',
                                ),
                              ),
                              const SizedBox(height: 8),
                              FilledButton.icon(
                                key: const Key('minor-continue-button'),
                                onPressed: _canContinueAsMinor
                                    ? widget.onContinue
                                    : null,
                                icon: const Icon(Icons.lock_open_outlined),
                                label: const Text(
                                  'Continue to the application',
                                ),
                              ),
                              TextButton(
                                onPressed: () => setState(() {
                                  _showUnder18Requirements = false;
                                  _guardianPermissionConfirmed = false;
                                  _organisationPermissionConfirmed = false;
                                  _noticeRead = false;
                                }),
                                child: const Text('Back to age options'),
                              ),
                            ],
                          ),
                        ),
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
  }
}

class _NoticeSection extends StatelessWidget {
  const _NoticeSection({
    required this.title,
    required this.body,
    this.isLast = false,
  });

  final String title;
  final String body;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(body),
        ],
      ),
    );
  }
}
