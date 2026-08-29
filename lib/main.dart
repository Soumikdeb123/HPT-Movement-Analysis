import 'package:flutter/material.dart';

void main() {
  runApp(const HPTApp());
}

class HPTApp extends StatelessWidget {
  const HPTApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'HPT Movement Analysis',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.green,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('HPT Movement Analysis'),
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.sports_tennis,
                size: 80,
              ),

              const SizedBox(height: 24),

              const Text(
                'Tennis Player Movement Analysis',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 12),

              const Text(
                'Analyse player movement from recorded tennis footage.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                ),
              ),

              const SizedBox(height: 32),

              ElevatedButton.icon(
                onPressed: () {
                  print('Select Tennis Video pressed');
                },
                icon: const Icon(Icons.video_file),
                label: const Text('Select Tennis Video'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}