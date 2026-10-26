#!/usr/bin/env python3
"""
Tennis Match Analysis Application
================================

This application analyzes tennis match footage to:
1. Detect tennis court keypoints
2. Calculate bird's eye view homography
3. Track player movements
4. Calculate distance covered by each player

Usage:
    python main.py --input video.mp4 --output results/
"""
from typing import Dict
import argparse
import os
import sys
import json
import matplotlib.pyplot as plt
import numpy as np

# Import our modules
from court_detector import CourtDetector
from player_tracker import PlayerTracker

class TennisMatchAnalyzer:
    def __init__(self, model_path: str = 'yolov8x.pt'):
        """
        Initialize the tennis match analyzer with all components
        """
        self.court_detector = CourtDetector()
        self.player_tracker = PlayerTracker(model_path)
        
    def analyze_match(self, video_path: str, output_dir: str = "results") -> Dict:
        """
        Complete analysis of a tennis match video
        
        Args:
            video_path: Path to input video file
            output_dir: Directory to save results
            
        Returns:
            Dictionary containing all analysis results
        """
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f"{output_dir}/videos", exist_ok=True)
        os.makedirs(f"{output_dir}/plots", exist_ok=True)
        os.makedirs(f"{output_dir}/data", exist_ok=True)
        
        print("Starting tennis match analysis...")
        print(f"Input video: {video_path}")
        print(f"Output directory: {output_dir}")
        
        # Step 1: Court Detection and Homography
        print("\n1. Detecting court and calculating homography...")
        court_results = self._detect_court_and_homography(video_path, output_dir)
        
        # Step 2: Player Tracking
        print("\n2. Tracking players...")
        tracking_results = self._track_players(video_path, output_dir, court_results)
        
        # Step 3: Distance Analysis
        print("\n3. Analyzing player movements and distances...")
        distance_results = self._analyze_distances(tracking_results, output_dir)
        
        # Step 4: Generate Comprehensive Report
        print("\n4. Generating comprehensive report...")
        final_report = self._generate_comprehensive_report(
            court_results, tracking_results, distance_results, output_dir
        )
        
        print(f"\nAnalysis complete! Results saved to: {output_dir}")
        return final_report
    
    def _detect_court_and_homography(self, video_path: str, output_dir: str) -> Dict:
        """Detect court corners and calculate separate metric/visual homographies."""
        import cv2

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise ValueError("Could not read video frame")

        court_corners = self.court_detector.detect_court_corners_perspective(frame)
        if court_corners is None:
            raise ValueError("Could not detect tennis court in video")

        # H_metric maps video pixels to metres. H_visual maps video pixels to
        # pixels in a separate bird's-eye image. They must not be interchanged.
        metric_homography = self.court_detector.get_court_transform_matrix(court_corners)
        visual_homography = self.court_detector.get_birds_eye_transform_matrix(court_corners)

        court_viz = self.court_detector.draw_court_analysis(frame, court_corners)
        court_detection_path = os.path.join(output_dir, "court_detection.jpg")
        cv2.imwrite(court_detection_path, court_viz)

        birds_eye_path = os.path.join(output_dir, "birds_eye_view.jpg")
        if visual_homography is not None:
            target_width, target_height = (600, 1300)
            birds_eye_frame = cv2.warpPerspective(
                frame, visual_homography, (target_width, target_height)
            )
            cv2.imwrite(birds_eye_path, birds_eye_frame)
        else:
            print("Warning: Could not calculate bird's-eye transform")
            birds_eye_path = None

        dimensions = self.court_detector.court_dimensions
        return {
            'court_corners': np.asarray(court_corners).tolist(),
            # Keep this legacy key as the metric matrix so older report readers
            # do not silently receive the image-warp matrix.
            'homography_matrix': metric_homography.tolist() if metric_homography is not None else None,
            'metric_homography_matrix': metric_homography.tolist() if metric_homography is not None else None,
            'birds_eye_homography_matrix': visual_homography.tolist() if visual_homography is not None else None,
            'court_dimensions_m': {
                'singles_width': float(dimensions['singles_width']),
                'singles_length': float(dimensions['singles_length']),
                'doubles_width': float(dimensions['doubles_width']),
                'doubles_length': float(dimensions['doubles_length']),
            },
            'court_detection_image': court_detection_path,
            'birds_eye_image': birds_eye_path,
        }

    def _track_players(self, video_path: str, output_dir: str, court_results: Dict) -> Dict:
        """Track players using the metric court homography when available."""
        output_video = os.path.join(output_dir, "videos", "tracked_players.mp4")
        matrix_data = court_results.get('metric_homography_matrix')
        metric_matrix = np.asarray(matrix_data, dtype=np.float64) if matrix_data is not None else None
        dimensions = court_results.get('court_dimensions_m', {})
        self.player_tracker.set_calibration(
            metric_matrix,
            court_width_m=dimensions.get('doubles_width', 10.97),
            court_length_m=dimensions.get('doubles_length', 23.77),
        )

        tracking_results = self.player_tracker.process_video(video_path, output_video)
        tracking_data_file = os.path.join(output_dir, "data", "tracking_data.json")
        self.player_tracker.save_tracking_data(tracking_data_file)
        return {
            'tracking_results': tracking_results,
            'tracking_video': output_video,
            'tracking_data': tracking_data_file,
        }

    def _analyze_distances(self, tracking_results: Dict, output_dir: str) -> Dict:
        """Prepare movement metrics without rough pixel-to-metre conversion."""
        stats = tracking_results['tracking_results']['track_statistics']
        distance_analysis = {}
        for track_id, track_stats in stats.items():
            distance_analysis[str(track_id)] = {
                'total_distance_pixels': track_stats['total_distance_pixels'],
                'total_distance_meters': track_stats['total_distance_meters'],
                'average_speed_pixels_per_frame': track_stats['average_speed_pixels_per_frame'],
                'average_speed_meters_per_second': track_stats['average_speed_meters_per_second'],
                'max_deceleration_mps2': track_stats['max_deceleration_mps2'],
                'deceleration_efforts': track_stats['deceleration_efforts'],
                'high_intensity_deceleration_efforts': track_stats['high_intensity_deceleration_efforts'],
                'average_peak_deceleration_mps2': track_stats['average_peak_deceleration_mps2'],
                'num_detections': track_stats['num_detections'],
                'metric_calibrated': track_stats['metric_calibrated'],
            }

        self._plot_player_movements(output_dir)
        return distance_analysis

    def _plot_player_movements(self, output_dir: str):
        """Plot full trajectories and cumulative distance in honest units."""
        tracks = self.player_tracker.tracks
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'cyan']
        metric_available = self.player_tracker.homography_matrix is not None
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))

        for i, (track_id, track) in enumerate(tracks.items()):
            color = colors[i % len(colors)]
            if metric_available:
                valid_points = [p for p in track.trajectory_court if p is not None]
                if len(valid_points) > 1:
                    positions = np.asarray(valid_points, dtype=float)
                    ax1.plot(positions[:, 0], positions[:, 1], color=color,
                             label=f'Player {track_id}', linewidth=2)
                    ax1.scatter(positions[0, 0], positions[0, 1], color=color, s=45, marker='o')
                    ax1.scatter(positions[-1, 0], positions[-1, 1], color=color, s=45, marker='s')
                if len(track.frame_history) > 1 and len(track.cumulative_distance_history_m) == len(track.frame_history):
                    ax2.plot(track.frame_history, track.cumulative_distance_history_m,
                             color=color, label=f'Player {track_id}', linewidth=2)
            else:
                if len(track.trajectory_pixels) > 1:
                    positions = np.asarray(track.trajectory_pixels, dtype=float)
                    ax1.plot(positions[:, 0], positions[:, 1], color=color,
                             label=f'Player {track_id}', linewidth=2)
                    ax1.scatter(positions[0, 0], positions[0, 1], color=color, s=45, marker='o')
                    ax1.scatter(positions[-1, 0], positions[-1, 1], color=color, s=45, marker='s')
                if len(track.frame_history) > 1 and len(track.cumulative_distance_history_pixels) == len(track.frame_history):
                    ax2.plot(track.frame_history, track.cumulative_distance_history_pixels,
                             color=color, label=f'Player {track_id}', linewidth=2)

        ax1.set_title('Player Movement Trajectories')
        ax1.set_xlabel('Court X (m)' if metric_available else 'X Position (pixels)')
        ax1.set_ylabel('Court Y (m)' if metric_available else 'Y Position (pixels)')
        if metric_available:
            ax1.set_xlim(0, self.player_tracker.court_width_m)
            ax1.set_ylim(self.player_tracker.court_length_m, 0)
            ax1.set_aspect('equal', adjustable='box')
        ax1.grid(True)
        if tracks:
            ax1.legend()

        ax2.set_title('Cumulative Distance Over Time')
        ax2.set_xlabel('Frame Number')
        ax2.set_ylabel('Cumulative distance (m)' if metric_available else 'Cumulative distance (pixels)')
        ax2.grid(True)
        if tracks:
            ax2.legend()

        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, 'plots', 'player_movements.png'), dpi=200, bbox_inches='tight')
        plt.close(fig)

        if metric_available:
            self._plot_deceleration(output_dir)

    def _plot_deceleration(self, output_dir: str):
        """Plot speed and acceleration per player, highlighting deceleration efforts."""
        tracker = self.player_tracker
        tracks = {tid: t for tid, t in tracker.tracks.items()
                  if any(a is not None for a in t.acceleration_history_mps2)}
        if not tracks:
            return
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'cyan']
        fps = tracker.fps
        fig, axes = plt.subplots(len(tracks), 1, figsize=(16, 4.5 * len(tracks)), squeeze=False)

        for ax, (i, (track_id, track)) in zip(axes[:, 0], enumerate(tracks.items())):
            color = colors[i % len(colors)]
            times = np.asarray(track.frame_history, dtype=float) / fps
            speed = np.asarray([np.nan if v is None else v for v in track.speed_history_mps])
            accel = np.asarray([np.nan if v is None else v for v in track.acceleration_history_mps2])

            ax.plot(times, accel, color=color, linewidth=1.5, label='Acceleration (m/s²)')
            ax.axhline(0, color='black', linewidth=0.8)
            ax.axhline(-tracker.deceleration_threshold_mps2, color='orange', linestyle='--', linewidth=1,
                       label=f'Deceleration threshold (-{tracker.deceleration_threshold_mps2:g} m/s²)')
            ax.axhline(-tracker.high_intensity_deceleration_mps2, color='red', linestyle='--', linewidth=1,
                       label=f'High intensity (-{tracker.high_intensity_deceleration_mps2:g} m/s²)')
            for effort in track.deceleration_efforts:
                ax.axvspan(effort['start_frame'] / fps, effort['end_frame'] / fps,
                           color='red' if effort['high_intensity'] else 'orange', alpha=0.2)
            ax.set_ylabel('Acceleration (m/s²)')
            ax.grid(True)

            speed_ax = ax.twinx()
            speed_ax.plot(times, speed, color='gray', linewidth=1, alpha=0.7, label='Speed (m/s)')
            speed_ax.set_ylabel('Speed (m/s)')

            ax.set_title(f'Player {track_id}: speed and deceleration '
                         f'({len(track.deceleration_efforts)} efforts)')
            handles, labels = ax.get_legend_handles_labels()
            speed_handles, speed_labels = speed_ax.get_legend_handles_labels()
            ax.legend(handles + speed_handles, labels + speed_labels, loc='upper right', fontsize=8)

        axes[-1, 0].set_xlabel('Time (s)')
        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, 'plots', 'player_deceleration.png'), dpi=150, bbox_inches='tight')
        plt.close(fig)

    def _generate_comprehensive_report(self, court_results: Dict, tracking_results: Dict, 
                                     distance_results: Dict, output_dir: str) -> Dict:
        """Generate comprehensive analysis report"""
        
        # Compile all results
        report = {
            'analysis_metadata': {
                'timestamp': str(np.datetime64('now')),
                'output_directory': output_dir
            },
            'court_analysis': court_results,
            'player_tracking': tracking_results,
            'distance_analysis': distance_results,
            'summary': {}
        }
        
        # Generate summary statistics
        total_players = len(distance_results)
        calibrated_distances = [result['total_distance_meters'] for result in distance_results.values()
                                if result.get('total_distance_meters') is not None]
        total_distance = float(sum(calibrated_distances)) if calibrated_distances else None
        avg_distance = (total_distance / len(calibrated_distances)) if calibrated_distances else None
        
        report['summary'] = {
            'total_players_detected': total_players,
            'total_distance_covered_meters': total_distance,
            'average_distance_per_calibrated_player_meters': avg_distance,
            'distance_calibration_available': bool(calibrated_distances),
            'court_detected': court_results.get('court_corners') is not None,
            'homography_calculated': court_results.get('metric_homography_matrix') is not None
        }
        
        # Save comprehensive report
        report_file = f"{output_dir}/comprehensive_analysis_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Generate text summary
        self._generate_text_summary(report, output_dir)
        
        return report
    
    def _generate_text_summary(self, report: Dict, output_dir: str):
        """Generate a readable summary that distinguishes calibrated from pixel data."""
        summary = report['summary']
        if summary.get('distance_calibration_available'):
            total_text = f"{summary['total_distance_covered_meters']:.2f} m"
            average_text = f"{summary['average_distance_per_calibrated_player_meters']:.2f} m"
        else:
            total_text = "Unavailable (court calibration failed)"
            average_text = "Unavailable (court calibration failed)"

        text_summary = f"""
TENNIS MATCH ANALYSIS REPORT
============================

Analysis Summary:
- Tracks with sufficient detections: {summary['total_players_detected']}
- Total calibrated distance: {total_text}
- Average distance per calibrated track: {average_text}
- Court detection: {'Successful' if summary['court_detected'] else 'Failed'}
- Metric homography: {'Successful' if summary['homography_calculated'] else 'Failed'}

Player Details:
"""
        for track_id, stats in report['distance_analysis'].items():
            distance = stats.get('total_distance_meters')
            speed = stats.get('average_speed_meters_per_second')
            distance_text = f"{distance:.2f} m" if distance is not None else "Unavailable (not calibrated)"
            speed_text = f"{speed:.2f} m/s" if speed is not None else "Unavailable (needs calibration and valid FPS)"
            max_decel = stats.get('max_deceleration_mps2')
            if max_decel is not None:
                avg_peak = stats.get('average_peak_deceleration_mps2')
                avg_peak_text = f"{avg_peak:.2f} m/s^2" if avg_peak is not None else "n/a"
                decel_text = (f"max {max_decel:.2f} m/s^2, {stats['deceleration_efforts']} efforts "
                              f"({stats['high_intensity_deceleration_efforts']} high intensity), "
                              f"average peak {avg_peak_text}")
            else:
                decel_text = "Unavailable (needs calibration and valid FPS)"
            text_summary += f"""
Player {track_id}:
- Total distance: {distance_text}
- Average speed: {speed_text}
- Deceleration: {decel_text}
- Pixel distance (debug only): {stats['total_distance_pixels']:.1f} px
- Number of detections: {stats['num_detections']}
"""

        birds_eye_image = report['court_analysis'].get('birds_eye_image') or 'Unavailable'
        text_summary += f"""
Output Files:
- Court detection: {report['court_analysis']['court_detection_image']}
- Bird's-eye view: {birds_eye_image}
- Player tracking video: {report['player_tracking']['tracking_video']}
- Movement plots: {output_dir}/plots/player_movements.png
- Deceleration plot: {output_dir}/plots/player_deceleration.png
- Tracking data: {report['player_tracking']['tracking_data']}
- Comprehensive report: {output_dir}/comprehensive_analysis_report.json

Note: Distances in metres are estimates based on the detected court corners and a planar homography.
Check court_detection.jpg to confirm the detected corners are correct. The player ground point is
estimated from the bottom-centre of each bounding box, so results are not survey-grade measurements.
Deceleration = rate of speed decrease from smoothed court positions. An effort is a stretch of at least
0.2 s with deceleration of 2 m/s^2 or more; high intensity means its peak reached 3 m/s^2. Far-court
players are measured less precisely (one pixel spans more court there), so treat their values with care.
"""
        with open(os.path.join(output_dir, 'analysis_summary.txt'), 'w', encoding='utf-8') as f:
            f.write(text_summary)
        print(text_summary)


def main():
    """Main function to run the tennis match analyzer"""
    parser = argparse.ArgumentParser(description='Analyze tennis match footage')
    parser.add_argument('--input', '-i', required=True, 
                       help='Input video file path')
    parser.add_argument('--output', '-o', default='results',
                       help='Output directory for results')
    parser.add_argument('--model', '-m', default='yolov8x.pt',
                       help='YOLO model path')
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' does not exist")
        sys.exit(1)
    
    try:
        # Initialize analyzer
        analyzer = TennisMatchAnalyzer(args.model)
        
        # Run analysis
        results = analyzer.analyze_match(args.input, args.output)
        
        print(f"\nAnalysis completed successfully!")
        print(f"Results saved to: {args.output}")
        
    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 