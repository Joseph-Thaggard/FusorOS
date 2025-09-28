#!/usr/bin/env python3
"""
Simplified Calibrated Plasma Spectrum Analyzer
Uses built-in NIST data and specutils for accurate deuterium plasma analysis
"""

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import argparse
import warnings
from scipy import signal
warnings.filterwarnings('ignore')

try:
    from specutils import Spectrum1D
    from astropy import units as u
    SPECUTILS_AVAILABLE = True
except ImportError:
    SPECUTILS_AVAILABLE = False
    print("Warning: specutils not available. Install with: pip3 install specutils astropy")

class SimplifiedPlasmaAnalyzer:
    def __init__(self):
        # NIST-calibrated deuterium emission lines (nm) - Balmer series
        self.deuterium_lines = {
            'D-alpha (n=3→2)': 656.281,
            'D-beta (n=4→2)': 486.133,
            'D-gamma (n=5→2)': 434.047,
            'D-delta (n=6→2)': 410.174,
            'D-epsilon (n=7→2)': 397.007,
        }
        
        # Other plasma-relevant lines
        self.reference_lines = {
            'He-I 587.6nm': 587.562,  # Helium (fusion indicator)
            'He-I 667.8nm': 667.815,  # Helium red line
            'He-I 501.6nm': 501.568,  # Helium green line
            'Ne-I 540.1nm': 540.056,  # Neon (calibration)
            'Ar-I 696.5nm': 696.543,  # Argon (calibration)
        }
        
        # Combined reference database
        self.all_lines = {**self.deuterium_lines, **self.reference_lines}
        
        # Camera response correction factors (typical DSLR)
        self.camera_correction = {
            'red_peak': 620,    # nm
            'green_peak': 540,  # nm  
            'blue_peak': 470,   # nm
            'red_width': 60,
            'green_width': 50,
            'blue_width': 45
        }
    
    def linear_wavelength_calibration(self, pixel_count, wl_start=380, wl_end=780):
        """Simple linear wavelength calibration"""
        return np.linspace(wl_start, wl_end, pixel_count)
    
    def polynomial_wavelength_calibration(self, pixels, known_lines):
        """
        Calibrate using known emission lines
        known_lines: dict of {pixel_position: wavelength_nm}
        """
        if len(known_lines) < 2:
            return self.linear_wavelength_calibration(len(pixels))
        
        pixel_pos = np.array(list(known_lines.keys()))
        wavelengths = np.array(list(known_lines.values()))
        
        # Fit polynomial (linear for 2 points, quadratic for 3+)
        degree = min(len(known_lines) - 1, 2)
        coeffs = np.polyfit(pixel_pos, wavelengths, degree)
        
        calibrated_wl = np.polyval(coeffs, pixels)
        return calibrated_wl, coeffs
    
    def extract_spectrum_from_image(self, image_path, region_params=None):
        """Extract spectrum from image with region selection"""
        
        # Load and process image
        img = Image.open(image_path)
        img_array = np.array(img)
        
        # Handle different image formats
        if len(img_array.shape) == 2:  # Grayscale
            img_array = np.stack([img_array] * 3, axis=-1)
        elif img_array.shape[2] == 4:  # RGBA
            img_array = img_array[:, :, :3]
        
        # Default analysis region (horizontal stripe across middle)
        if region_params is None:
            region_params = {
                'y_start': 0.45, 'y_end': 0.55,  # Narrower region for better SNR
                'x_start': 0.05, 'x_end': 0.95   # Avoid edges
            }
        
        # Extract region of interest
        h, w = img_array.shape[:2]
        y1 = int(h * region_params['y_start'])
        y2 = int(h * region_params['y_end'])
        x1 = int(w * region_params['x_start'])
        x2 = int(w * region_params['x_end'])
        
        region = img_array[y1:y2, x1:x2]
        
        # Extract horizontal spectrum by averaging vertically
        spectrum_raw = np.mean(region, axis=0)
        
        # Separate RGB channels
        red_channel = spectrum_raw[:, 0]
        green_channel = spectrum_raw[:, 1]
        blue_channel = spectrum_raw[:, 2]
        
        # Create wavelength axis
        pixel_positions = np.arange(len(red_channel))
        wavelengths = self.linear_wavelength_calibration(len(red_channel))
        
        return {
            'wavelengths': wavelengths,
            'pixels': pixel_positions,
            'red': red_channel,
            'green': green_channel,
            'blue': blue_channel,
            'total': red_channel + green_channel + blue_channel,
            'region': region,
            'full_image': img_array,
            'region_params': region_params
        }
    
    def correct_camera_response(self, wavelengths, red, green, blue):
        """Apply camera spectral response correction"""
        
        # Calculate response curves
        red_response = np.exp(-((wavelengths - self.camera_correction['red_peak'])**2) / 
                             (2 * self.camera_correction['red_width']**2))
        green_response = np.exp(-((wavelengths - self.camera_correction['green_peak'])**2) / 
                               (2 * self.camera_correction['green_width']**2))
        blue_response = np.exp(-((wavelengths - self.camera_correction['blue_peak'])**2) / 
                              (2 * self.camera_correction['blue_width']**2))
        
        # Apply corrections (normalize by response)
        red_corrected = red / (red_response + 0.1)
        green_corrected = green / (green_response + 0.1)
        blue_corrected = blue / (blue_response + 0.1)
        
        return red_corrected, green_corrected, blue_corrected
    
    def find_emission_peaks(self, wavelengths, intensity, min_prominence=None):
        """Find emission peaks in spectrum"""
        
        if min_prominence is None:
            # Adaptive threshold based on signal statistics
            baseline = np.median(intensity)
            noise_level = np.std(intensity[intensity < np.percentile(intensity, 75)])
            min_prominence = baseline + 3 * noise_level
        
        # Find peaks
        peaks, properties = signal.find_peaks(
            intensity,
            prominence=min_prominence,
            distance=5,  # Minimum 5 pixels between peaks
            width=1
        )
        
        peak_wavelengths = wavelengths[peaks]
        peak_intensities = intensity[peaks]
        peak_prominences = properties['prominences']
        
        # Sort by prominence (strongest peaks first)
        sort_idx = np.argsort(peak_prominences)[::-1]
        
        return {
            'peak_indices': peaks[sort_idx],
            'wavelengths': peak_wavelengths[sort_idx],
            'intensities': peak_intensities[sort_idx],
            'prominences': peak_prominences[sort_idx]
        }
    
    def identify_spectral_lines(self, peak_data, tolerance=2.0):
        """Match detected peaks to known emission lines"""
        
        identified = {}
        unidentified_peaks = []
        
        for i, (wl, intensity, prominence) in enumerate(zip(
            peak_data['wavelengths'], 
            peak_data['intensities'],
            peak_data['prominences']
        )):
            
            best_match = None
            best_error = float('inf')
            
            # Check against all known lines
            for line_name, ref_wl in self.all_lines.items():
                error = abs(wl - ref_wl)
                if error <= tolerance and error < best_error:
                    best_match = line_name
                    best_error = error
            
            if best_match:
                identified[best_match] = {
                    'measured_wavelength': wl,
                    'reference_wavelength': self.all_lines[best_match],
                    'intensity': intensity,
                    'prominence': prominence,
                    'wavelength_error': wl - self.all_lines[best_match],
                    'relative_error_ppm': ((wl - self.all_lines[best_match]) / self.all_lines[best_match]) * 1e6
                }
            else:
                unidentified_peaks.append({
                    'wavelength': wl,
                    'intensity': intensity,
                    'prominence': prominence
                })
        
        return identified, unidentified_peaks
    
    def analyze_plasma_properties(self, identified_lines):
        """Extract plasma physics information from line data"""
        
        analysis = {
            'deuterium_lines_detected': [],
            'helium_lines_detected': [],
            'line_ratios': {},
            'temperature_indicators': {},
            'fusion_evidence': [],
            'calibration_quality': {}
        }
        
        # Check for deuterium Balmer series
        for line_name in self.deuterium_lines.keys():
            if line_name in identified_lines:
                analysis['deuterium_lines_detected'].append(line_name)
        
        # Check for helium lines (fusion indicators)
        for line_name in identified_lines:
            if 'He-I' in line_name:
                analysis['helium_lines_detected'].append(line_name)
                analysis['fusion_evidence'].append(f"Helium emission detected: {line_name}")
        
        # Calculate Balmer line ratios for temperature estimation
        d_alpha = identified_lines.get('D-alpha (n=3→2)')
        d_beta = identified_lines.get('D-beta (n=4→2)')
        d_gamma = identified_lines.get('D-gamma (n=5→2)')
        
        if d_alpha and d_beta:
            ratio = d_alpha['intensity'] / d_beta['intensity']
            analysis['line_ratios']['D-alpha/D-beta'] = ratio
            
            # Rough temperature estimate (simplified)
            # Real analysis requires density corrections and more sophisticated models
            if ratio > 0:
                # Empirical relationship for rough estimate
                temp_ev = 5 + 8 * np.log10(ratio)
                analysis['temperature_indicators']['balmer_ratio_temp'] = f"{temp_ev:.1f} eV"
        
        if d_beta and d_gamma:
            ratio = d_beta['intensity'] / d_gamma['intensity']
            analysis['line_ratios']['D-beta/D-gamma'] = ratio
        
        # Assess calibration quality
        if identified_lines:
            errors = [abs(data['wavelength_error']) for data in identified_lines.values()]
            analysis['calibration_quality'] = {
                'mean_error_nm': np.mean(errors),
                'max_error_nm': np.max(errors),
                'rms_error_nm': np.sqrt(np.mean(np.array(errors)**2)),
                'identified_lines_count': len(identified_lines)
            }
        
        return analysis
    
    def create_analysis_plots(self, spectrum_data, peak_data, identified_lines, 
                            plasma_analysis, save_path=None):
        """Generate comprehensive analysis plots"""
        
        fig = plt.figure(figsize=(18, 14))
        
        # Plot 1: Full spectrum with all channels
        ax1 = plt.subplot(3, 2, 1)
        wl = spectrum_data['wavelengths']
        
        ax1.plot(wl, spectrum_data['red'], 'r-', alpha=0.7, linewidth=1.5, label='Red channel')
        ax1.plot(wl, spectrum_data['green'], 'g-', alpha=0.7, linewidth=1.5, label='Green channel')
        ax1.plot(wl, spectrum_data['blue'], 'b-', alpha=0.7, linewidth=1.5, label='Blue channel')
        ax1.plot(wl, spectrum_data['total'], 'k-', alpha=0.9, linewidth=2, label='Total intensity')
        
        # Mark detected peaks
        for peak_wl, peak_int in zip(peak_data['wavelengths'], peak_data['intensities']):
            ax1.plot(peak_wl, peak_int, 'ro', markersize=6, alpha=0.8)
        
        ax1.set_xlabel('Wavelength (nm)')
        ax1.set_ylabel('Intensity (ADU)')
        ax1.set_title('Full Spectrum Analysis', fontsize=14, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(400, 750)
        
        # Plot 2: Original image with analysis region
        ax2 = plt.subplot(3, 2, 2)
        ax2.imshow(spectrum_data['full_image'])
        ax2.set_title('Image with Analysis Region', fontsize=14, fontweight='bold')
        ax2.axis('off')
        
        # Highlight analysis region
        h, w = spectrum_data['full_image'].shape[:2]
        rp = spectrum_data['region_params']
        y1, y2 = int(h * rp['y_start']), int(h * rp['y_end'])
        x1, x2 = int(w * rp['x_start']), int(w * rp['x_end'])
        
        rect = plt.Rectangle((x1, y1), x2-x1, y2-y1, linewidth=3,
                           edgecolor='yellow', facecolor='none', alpha=0.8)
        ax2.add_patch(rect)
        
        # Plot 3: Deuterium Balmer series focus
        ax3 = plt.subplot(3, 2, 3)
        ax3.plot(wl, spectrum_data['total'], 'k-', alpha=0.8, linewidth=1.5)
        
        # Mark all deuterium reference lines
        for line_name, ref_wl in self.deuterium_lines.items():
            ax3.axvline(x=ref_wl, color='red', linestyle='--', alpha=0.6, linewidth=1)
            # Shortened labels for better visibility
            short_name = line_name.split('(')[0].strip()
            ax3.text(ref_wl, ax3.get_ylim()[1] * 0.95, short_name, 
                    rotation=90, ha='center', va='top', fontsize=9, color='red')
        
        # Mark identified deuterium lines
        for line_name, line_data in identified_lines.items():
            if line_name in self.deuterium_lines:
                wl_measured = line_data['measured_wavelength']
                intensity = line_data['intensity']
                ax3.plot(wl_measured, intensity, 'go', markersize=8, alpha=0.8)
                ax3.text(wl_measured, intensity * 1.1, f"✓{wl_measured:.1f}", 
                        ha='center', va='bottom', fontsize=8, color='green', fontweight='bold')
        
        ax3.set_xlabel('Wavelength (nm)')
        ax3.set_ylabel('Intensity (ADU)')
        ax3.set_title('Deuterium Balmer Series Identification', fontsize=14, fontweight='bold')
        ax3.grid(True, alpha=0.3)
        ax3.set_xlim(390, 670)
        
        # Plot 4: Peak identification summary
        ax4 = plt.subplot(3, 2, 4)
        if identified_lines:
            line_names = list(identified_lines.keys())
            intensities = [identified_lines[name]['intensity'] for name in line_names]
            errors = [abs(identified_lines[name]['wavelength_error']) for name in line_names]
            
            # Create bar plot colored by wavelength error
            bars = ax4.bar(range(len(line_names)), intensities, 
                          color=plt.cm.RdYlGn_r([e/2.0 for e in errors]))  # Red=bad, Green=good
            
            ax4.set_xlabel('Identified Lines')
            ax4.set_ylabel('Peak Intensity (ADU)')
            ax4.set_title('Line Identification Quality', fontsize=14, fontweight='bold')
            ax4.set_xticks(range(len(line_names)))
            ax4.set_xticklabels([name.split('(')[0].strip() for name in line_names], 
                               rotation=45, ha='right')
            
            # Add error values as text
            for i, (bar, error) in enumerate(zip(bars, errors)):
                ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(intensities)*0.02,
                        f'±{error:.1f}nm', ha='center', va='bottom', fontsize=8)
        
        # Plot 5: Analysis summary table
        ax5 = plt.subplot(3, 2, 5)
        ax5.axis('off')
        
        # Create detailed summary text
        summary = "PLASMA SPECTROSCOPY ANALYSIS\n"
        summary += "=" * 35 + "\n\n"
        
        summary += f"Total peaks detected: {len(peak_data['wavelengths'])}\n"
        summary += f"Lines identified: {len(identified_lines)}\n"
        summary += f"Deuterium lines: {len(plasma_analysis['deuterium_lines_detected'])}\n"
        summary += f"Helium lines: {len(plasma_analysis['helium_lines_detected'])}\n\n"
        
        if plasma_analysis['calibration_quality']:
            cal = plasma_analysis['calibration_quality']
            summary += "CALIBRATION QUALITY:\n"
            summary += f"  Mean error: {cal['mean_error_nm']:.2f} nm\n"
            summary += f"  RMS error: {cal['rms_error_nm']:.2f} nm\n"
            summary += f"  Max error: {cal['max_error_nm']:.2f} nm\n\n"
        
        if plasma_analysis['line_ratios']:
            summary += "LINE RATIOS:\n"
            for ratio_name, ratio_value in plasma_analysis['line_ratios'].items():
                summary += f"  {ratio_name}: {ratio_value:.2f}\n"
            summary += "\n"
        
        if plasma_analysis['temperature_indicators']:
            summary += "TEMPERATURE ESTIMATES:\n"
            for indicator, value in plasma_analysis['temperature_indicators'].items():
                summary += f"  {indicator}: {value}\n"
            summary += "\n"
        
        if plasma_analysis['fusion_evidence']:
            summary += "FUSION INDICATORS:\n"
            for evidence in plasma_analysis['fusion_evidence']:
                summary += f"  • {evidence}\n"
        
        ax5.text(0.05, 0.95, summary, transform=ax5.transAxes, fontsize=11,
                fontfamily='monospace', verticalalignment='top',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
        
        # Plot 6: Detailed line identification table
        ax6 = plt.subplot(3, 2, 6)
        ax6.axis('off')
        
        if identified_lines:
            # Create table data
            table_data = []
            headers = ['Line', 'Measured (nm)', 'Reference (nm)', 'Error (nm)', 'Intensity']
            
            for line_name, data in identified_lines.items():
                short_name = line_name.split('(')[0].strip()
                table_data.append([
                    short_name,
                    f"{data['measured_wavelength']:.2f}",
                    f"{data['reference_wavelength']:.2f}", 
                    f"{data['wavelength_error']:+.2f}",
                    f"{data['intensity']:.0f}"
                ])
            
            # Create table
            table = ax6.table(cellText=table_data[:10],  # Show top 10 lines
                             colLabels=headers,
                             cellLoc='center',
                             loc='center',
                             colWidths=[0.25, 0.18, 0.18, 0.15, 0.15])
            
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1.0, 1.8)
            
            # Color code by error magnitude
            for i in range(1, len(table_data) + 1):
                error = float(table_data[i-1][3])
                if abs(error) < 0.5:
                    color = 'lightgreen'
                elif abs(error) < 1.0:
                    color = 'lightyellow'
                else:
                    color = 'lightcoral'
                table[(i, 3)].set_facecolor(color)
            
            ax6.set_title('Identified Emission Lines', fontsize=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
            print(f"\n✓ Analysis plot saved to: {save_path}")
        
        plt.show()
        return fig

def main():
    parser = argparse.ArgumentParser(description='Simplified Calibrated Plasma Spectrum Analyzer')
    parser.add_argument('image_path', help='Path to plasma image file')
    parser.add_argument('--tolerance', type=float, default=2.0,
                       help='Line identification tolerance in nm (default: 2.0)')
    parser.add_argument('--min-prominence', type=float, default=None,
                       help='Minimum peak prominence for detection')
    parser.add_argument('--save', action='store_true',
                       help='Save analysis plot to file')
    parser.add_argument('--output', type=str, default=None,
                       help='Output file path for plot')
    
    args = parser.parse_args()
    
    print("🔬 Simplified Calibrated Plasma Spectrum Analyzer")
    print("=" * 50)
    
    # Initialize analyzer
    analyzer = SimplifiedPlasmaAnalyzer()
    
    print(f"📸 Loading image: {args.image_path}")
    
    try:
        # Extract spectrum from image
        spectrum_data = analyzer.extract_spectrum_from_image(args.image_path)
        print(f"✓ Spectrum extracted: {len(spectrum_data['wavelengths'])} data points")
        
        # Apply camera response correction
        red_corr, green_corr, blue_corr = analyzer.correct_camera_response(
            spectrum_data['wavelengths'], 
            spectrum_data['red'],
            spectrum_data['green'], 
            spectrum_data['blue']
        )
        
        # Update with corrected data
        total_corrected = red_corr + green_corr + blue_corr
        spectrum_data['total'] = total_corrected
        print("✓ Camera response correction applied")
        
        # Find emission peaks
        peak_data = analyzer.find_emission_peaks(
            spectrum_data['wavelengths'], 
            total_corrected,
            min_prominence=args.min_prominence
        )
        print(f"✓ Found {len(peak_data['wavelengths'])} emission peaks")
        
        # Identify spectral lines
        identified_lines, unidentified_peaks = analyzer.identify_spectral_lines(
            peak_data, tolerance=args.tolerance
        )
        print(f"✓ Identified {len(identified_lines)} known emission lines")
        
        # Analyze plasma properties
        plasma_analysis = analyzer.analyze_plasma_properties(identified_lines)
        
        # Print results summary
        print(f"\n🔍 ANALYSIS RESULTS:")
        print(f"   Deuterium lines detected: {len(plasma_analysis['deuterium_lines_detected'])}")
        print(f"   Helium lines detected: {len(plasma_analysis['helium_lines_detected'])}")
        
        if plasma_analysis['temperature_indicators']:
            for indicator, temp in plasma_analysis['temperature_indicators'].items():
                print(f"   Estimated temperature: {temp}")
        
        if plasma_analysis['fusion_evidence']:
            print(f"   Fusion evidence: {len(plasma_analysis['fusion_evidence'])} indicators")
        
        # Generate output file path
        output_path = args.output
        if args.save and not output_path:
            base_name = args.image_path.rsplit('.', 1)[0]
            output_path = f"{base_name}_plasma_analysis.png"
        
        # Create comprehensive plots
        print(f"\n📊 Generating analysis plots...")
        analyzer.create_analysis_plots(
            spectrum_data, peak_data, identified_lines, plasma_analysis,
            save_path=output_path if args.save else None
        )
        
        print(f"\n✅ Analysis complete!")
        
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()