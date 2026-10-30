"""
Analytical Energy Estimation Model for IoT Nodes.
Based on empirical radio frequency (RF) transceiver and microcontroller power profiles
(e.g., Texas Instruments CC2420 / Nordic nRF52840 IEEE 802.15.4 specifications).
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EnergyModelParameters:
    """
    Hardware energy profile parameters (in millijoules, mJ).
    Labled as an analytical estimation model, not direct hardware measurement.
    """
    tx_startup_energy_mj: float = 0.050       # Radio wake-up, PLL lock, preamble transmission
    tx_energy_per_byte_mj: float = 0.0012     # RF power consumption during byte transmission
    proc_energy_per_reading_mj: float = 0.0004 # MCU ADC sampling and data conversion
    batch_pack_energy_mj: float = 0.0008      # Memory buffer handling and frame serialization


def estimate_energy_consumption(
    num_packets_transmitted: int,
    total_bytes_transmitted: int,
    num_readings_generated: int,
    num_readings_delivered: int,
    params: EnergyModelParameters = EnergyModelParameters(),
) -> dict[str, float]:
    """
    Computes analytical energy estimate for sensor node operations.
    Returns breakdown and total estimated energy in millijoules (mJ).
    """
    # 1. Radio RF transmission energy
    radio_startup = num_packets_transmitted * params.tx_startup_energy_mj
    radio_tx_bytes = total_bytes_transmitted * params.tx_energy_per_byte_mj
    total_radio_energy = radio_startup + radio_tx_bytes

    # 2. MCU sensor processing & aggregation overhead
    sensor_proc_energy = num_readings_generated * params.proc_energy_per_reading_mj
    batch_pack_energy = num_packets_transmitted * params.batch_pack_energy_mj
    total_mcu_energy = sensor_proc_energy + batch_pack_energy

    # Total estimated energy in mJ
    total_energy_mj = total_radio_energy + total_mcu_energy
    
    # Energy efficiency per successfully delivered reading
    energy_per_delivered_reading_mj = (
        total_energy_mj / num_readings_delivered if num_readings_delivered > 0 else 0.0
    )

    return {
        "total_energy_mj": round(total_energy_mj, 4),
        "radio_energy_mj": round(total_radio_energy, 4),
        "mcu_energy_mj": round(total_mcu_energy, 4),
        "energy_per_delivered_reading_mj": round(energy_per_delivered_reading_mj, 5),
    }
