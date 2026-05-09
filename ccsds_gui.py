#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Wahyudi Hasbi

"""
ccsds_gui.py

Public GUI for ccsds-tm-tc-formatting-lab.

Full CCSDS path only:
- Configurable mission ID and CCSDS link fields
- Up to 50 numeric TM sensor inputs
- Up to 10 switch ON/OFF TC commands
- Up to 5 attitude pointing TC commands
- TM Space Packet -> RS/interleaving -> randomizer -> ASM/CADU
- Full RS decode trace
- TC Space Packet -> TC Transfer Frame -> FECF validation
"""

from __future__ import annotations

import json
import random
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path

from ccsds_packets import SpacePacketConfig, parse_space_packet_header, hex_bytes
from ccsds_rs import (
    E, J, RS_K, RS_N, RS_PARITY, RS_T, GF_PRIM_POLY,
    RS_FCR, RS_BETA_POWER, RS_GEN, hxlst
)
from ccsds_tm import (
    ASM, FILL_BYTE, INTERLEAVING_DEPTH, TMConfig,
    build_tm_space_packet, build_tm_cadu, receive_tm_cadu, flip_bits
)
from ccsds_tc import TCConfig, build_tc_space_packet, build_tc_transfer_frame, crc16_ccitt
from payloads import (
    Sensor, SwitchCommand, AttitudeCommand,
    build_tm_sensor_payload, build_tc_command_payload,
    MAX_SENSORS, MAX_SWITCH_COMMANDS, MAX_ATTITUDE_COMMANDS
)


APP_TITLE = "CCSDS TM/TC Formatting Lab"


def parse_int(text: str) -> int:
    return int(text.strip(), 0)


def parse_float(text: str) -> float:
    return float(text.strip())


def bit_marker(byte_value: int, bit_in_byte: int) -> str:
    bits = f"{byte_value:08b}"
    return bits[:bit_in_byte] + "'" + bits[bit_in_byte] + "'" + bits[bit_in_byte+1:]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x920")
        self.sensor_rows = []
        self.switch_rows = []
        self.attitude_rows = []
        self.last_report = {}
        self._build()

    def _build(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text=APP_TITLE, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="Full CCSDS path: Space Packet, TM RS/interleaving/randomizer/ASM, TC Transfer Frame/FECF. No simple model, no BCH/CLTU.",
        ).pack(anchor="w", pady=(0, 8))

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True)

        self.tab_config = ttk.Frame(self.nb, padding=8)
        self.tab_tm_input = ttk.Frame(self.nb, padding=8)
        self.tab_tc_input = ttk.Frame(self.nb, padding=8)
        self.tab_tm_output = ttk.Frame(self.nb, padding=8)
        self.tab_rs_trace = ttk.Frame(self.nb, padding=8)
        self.tab_tc_output = ttk.Frame(self.nb, padding=8)
        self.tab_bits = ttk.Frame(self.nb, padding=8)
        self.tab_constants = ttk.Frame(self.nb, padding=8)

        for tab, title in [
            (self.tab_config, "1 Mission / Link Configuration"),
            (self.tab_tm_input, "2 TM Sensor Input"),
            (self.tab_tc_input, "3 TC Command Input"),
            (self.tab_tm_output, "4 Build TM"),
            (self.tab_rs_trace, "5 Full RS Decode Trace"),
            (self.tab_tc_output, "6 Build TC"),
            (self.tab_bits, "7 Bit / Timing Explanation"),
            (self.tab_constants, "8 Constants and Field Definitions"),
        ]:
            self.nb.add(tab, text=title)

        self._build_config_tab()
        self._build_tm_input_tab()
        self._build_tc_input_tab()
        self.txt_tm = self._output_text(self.tab_tm_output)
        self.txt_rs = self._output_text(self.tab_rs_trace)
        self.txt_tc = self._output_text(self.tab_tc_output)
        self.txt_bits = self._output_text(self.tab_bits)
        self.txt_constants = self._output_text(self.tab_constants)

        self._set_text(self.txt_constants, self.constants_text())
        self.run_all()

    def _output_text(self, parent):
        t = scrolledtext.ScrolledText(parent, wrap="none", font=("Consolas", 10))
        t.pack(fill="both", expand=True)
        return t

    def _set_text(self, widget, text):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _build_config_tab(self):
        f = self.tab_config
        self.cfg_entries = {}
        groups = [
            ("Mission identity", [
                ("mission_id", "Mission ID text in Packet Data Field", "DEMO-SAT"),
            ]),
            ("Space Packet", [
                ("tm_apid", "TM APID, 0..2047", "100"),
                ("tm_seq", "TM Space Packet Sequence Count, 0..16383", "1"),
                ("tc_apid", "TC APID, 0..2047", "200"),
                ("tc_seq", "TC Space Packet Sequence Count, 0..16383", "7"),
            ]),
            ("TM channel coding", [
                ("tm_bitrate", "TM bitrate bps", "9600"),
                ("manual_tm_bits", "Manual TM bit positions after ASM is removed", "96,104,298"),
                ("random_tm_count", "Random TM bit count", "0"),
                ("random_seed", "Random seed", "100"),
            ]),
            ("TC Transfer Frame", [
                ("tc_bitrate", "TC bitrate bps", "1200"),
                ("tc_tfvn", "TFVN, 0..3", "0"),
                ("tc_bypass", "Bypass flag, 0/1", "0"),
                ("tc_control", "Control-command flag, 0/1", "0"),
                ("tc_scid", "SCID numeric, 0..1023", "0x2AA"),
                ("tc_vcid", "VCID numeric, 0..63", "0"),
                ("tc_frame_seq", "TC frame sequence number, 0..255", "7"),
                ("tc_include_fecf", "Include FECF? 1=yes, 0=no", "1"),
            ]),
        ]

        row = 0
        for title, items in groups:
            ttk.Label(f, text=title, font=("Segoe UI", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 4))
            row += 1
            for key, label, default in items:
                ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=2)
                e = ttk.Entry(f, width=34)
                e.insert(0, default)
                e.grid(row=row, column=1, sticky="w", pady=2)
                self.cfg_entries[key] = e
                row += 1

        btns = ttk.Frame(f)
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Button(btns, text="Run all", command=self.run_all).pack(side="left", padx=4)
        ttk.Button(btns, text="Save configuration JSON", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(btns, text="Load configuration JSON", command=self.load_config).pack(side="left", padx=4)
        ttk.Button(btns, text="Export last report JSON", command=self.export_report).pack(side="left", padx=4)

        explanation = scrolledtext.ScrolledText(f, wrap="word", height=16, font=("Consolas", 10))
        explanation.grid(row=row+1, column=0, columnspan=2, sticky="nsew", pady=8)
        explanation.insert("1.0",
"""Important: nothing here is hidden.

Mission ID text is application data inside the Packet Data Field.
SCID is a numeric 10-bit TC Transfer Frame field.
They are not the same.

Manual TM bit positions are relative to the randomized transmitted codeblock after the ASM is removed.
For example, bit 96 means byte_index = 96 // 8 = 12 and bit_inside_byte = 96 % 8 = 0.

TC BCH/CLTU and COP-1 are not implemented in this public version.
""")
        explanation.configure(state="disabled")
        f.columnconfigure(1, weight=1)
        f.rowconfigure(row+1, weight=1)

    def _build_tm_input_tab(self):
        top = ttk.Frame(self.tab_tm_input)
        top.pack(fill="x")
        ttk.Label(top, text=f"TM sensors: up to {MAX_SENSORS} enabled rows", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="Add sensor", command=self.add_sensor_row).pack(side="left", padx=8)
        ttk.Button(top, text="Run all", command=self.run_all).pack(side="left", padx=8)

        canvas = tk.Canvas(self.tab_tm_input)
        scroll = ttk.Scrollbar(self.tab_tm_input, orient="vertical", command=canvas.yview)
        self.sensor_frame = ttk.Frame(canvas)
        self.sensor_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sensor_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        headers = ["Use", "Name", "Value", "Unit", "Scale", "Parameter ID"]
        for c, h in enumerate(headers):
            ttk.Label(self.sensor_frame, text=h, font=("Segoe UI", 10, "bold")).grid(row=0, column=c, sticky="w", padx=4, pady=4)

        defaults = [
            ("BAT_V", "7.42", "V", "0.01", "0x0001"),
            ("BAT_I", "0.85", "A", "0.01", "0x0002"),
            ("SP_X", "0.31", "A", "0.01", "0x0003"),
            ("SP_Y", "0.28", "A", "0.01", "0x0004"),
            ("SP_Z", "0.35", "A", "0.01", "0x0005"),
        ]
        for d in defaults:
            self.add_sensor_row(*d)

    def add_sensor_row(self, name="", value="0.0", unit="", scale="0.01", pid="0x0001"):
        if len(self.sensor_rows) >= MAX_SENSORS:
            messagebox.showwarning(APP_TITLE, f"Maximum sensor rows is {MAX_SENSORS}")
            return
        r = len(self.sensor_rows) + 1
        enabled = tk.IntVar(value=1)
        cells = {
            "enabled": enabled,
            "name": ttk.Entry(self.sensor_frame, width=18),
            "value": ttk.Entry(self.sensor_frame, width=12),
            "unit": ttk.Entry(self.sensor_frame, width=8),
            "scale": ttk.Entry(self.sensor_frame, width=10),
            "pid": ttk.Entry(self.sensor_frame, width=10),
        }
        ttk.Checkbutton(self.sensor_frame, variable=enabled).grid(row=r, column=0, padx=4, pady=2)
        for col, key in enumerate(["name", "value", "unit", "scale", "pid"], start=1):
            cells[key].grid(row=r, column=col, padx=4, pady=2)
        cells["name"].insert(0, name)
        cells["value"].insert(0, value)
        cells["unit"].insert(0, unit)
        cells["scale"].insert(0, scale)
        cells["pid"].insert(0, pid)
        self.sensor_rows.append(cells)

    def _build_tc_input_tab(self):
        top = ttk.Frame(self.tab_tc_input)
        top.pack(fill="x")
        ttk.Label(top, text="TC commands", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="Add switch command", command=self.add_switch_row).pack(side="left", padx=8)
        ttk.Button(top, text="Add attitude command", command=self.add_attitude_row).pack(side="left", padx=8)
        ttk.Button(top, text="Run all", command=self.run_all).pack(side="left", padx=8)

        paned = ttk.Panedwindow(self.tab_tc_input, orient="vertical")
        paned.pack(fill="both", expand=True, pady=8)

        sw_box = ttk.Frame(paned, padding=4)
        att_box = ttk.Frame(paned, padding=4)
        paned.add(sw_box, weight=1)
        paned.add(att_box, weight=1)

        ttk.Label(sw_box, text=f"Switch ON/OFF commands, max {MAX_SWITCH_COMMANDS}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.switch_frame = ttk.Frame(sw_box)
        self.switch_frame.pack(fill="x")
        for c, h in enumerate(["Use", "Name", "Command ID", "State ON/OFF"]):
            ttk.Label(self.switch_frame, text=h, font=("Segoe UI", 10, "bold")).grid(row=0, column=c, sticky="w", padx=4, pady=4)

        ttk.Label(att_box, text=f"Attitude instruction commands, max {MAX_ATTITUDE_COMMANDS}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(att_box, text="Explanation: OBDH receives this command, then asks ADCS to point to X/Y/Z angles.").pack(anchor="w")
        self.attitude_frame = ttk.Frame(att_box)
        self.attitude_frame.pack(fill="x")
        for c, h in enumerate(["Use", "Name", "Command ID", "X deg", "Y deg", "Z deg"]):
            ttk.Label(self.attitude_frame, text=h, font=("Segoe UI", 10, "bold")).grid(row=0, column=c, sticky="w", padx=4, pady=4)

        self.add_switch_row("UHF_TX", "0x0001", "ON")
        self.add_switch_row("PAYLOAD", "0x0002", "OFF")
        self.add_attitude_row("POINT_TARGET_1", "0x0101", "10.5", "-2.0", "35.0")

    def add_switch_row(self, name="", cmd_id="0x0001", state="ON"):
        if len(self.switch_rows) >= MAX_SWITCH_COMMANDS:
            messagebox.showwarning(APP_TITLE, f"Maximum switch command rows is {MAX_SWITCH_COMMANDS}")
            return
        r = len(self.switch_rows) + 1
        enabled = tk.IntVar(value=1)
        cells = {
            "enabled": enabled,
            "name": ttk.Entry(self.switch_frame, width=18),
            "id": ttk.Entry(self.switch_frame, width=12),
            "state": tk.StringVar(value=state),
        }
        ttk.Checkbutton(self.switch_frame, variable=enabled).grid(row=r, column=0, padx=4, pady=2)
        cells["name"].grid(row=r, column=1, padx=4, pady=2)
        cells["id"].grid(row=r, column=2, padx=4, pady=2)
        ttk.Combobox(self.switch_frame, textvariable=cells["state"], values=["ON", "OFF"], state="readonly", width=10).grid(row=r, column=3, padx=4, pady=2)
        cells["name"].insert(0, name)
        cells["id"].insert(0, cmd_id)
        self.switch_rows.append(cells)

    def add_attitude_row(self, name="", cmd_id="0x0101", x="0.0", y="0.0", z="0.0"):
        if len(self.attitude_rows) >= MAX_ATTITUDE_COMMANDS:
            messagebox.showwarning(APP_TITLE, f"Maximum attitude command rows is {MAX_ATTITUDE_COMMANDS}")
            return
        r = len(self.attitude_rows) + 1
        enabled = tk.IntVar(value=1)
        cells = {
            "enabled": enabled,
            "name": ttk.Entry(self.attitude_frame, width=18),
            "id": ttk.Entry(self.attitude_frame, width=12),
            "x": ttk.Entry(self.attitude_frame, width=10),
            "y": ttk.Entry(self.attitude_frame, width=10),
            "z": ttk.Entry(self.attitude_frame, width=10),
        }
        ttk.Checkbutton(self.attitude_frame, variable=enabled).grid(row=r, column=0, padx=4, pady=2)
        for col, key in enumerate(["name", "id", "x", "y", "z"], start=1):
            cells[key].grid(row=r, column=col, padx=4, pady=2)
        cells["name"].insert(0, name)
        cells["id"].insert(0, cmd_id)
        cells["x"].insert(0, x)
        cells["y"].insert(0, y)
        cells["z"].insert(0, z)
        self.attitude_rows.append(cells)

    def collect_config(self):
        cfg = {k: e.get().strip() for k, e in self.cfg_entries.items()}
        sp_cfg = SpacePacketConfig()
        tm_cfg = TMConfig(
            tm_apid=parse_int(cfg["tm_apid"]),
            tm_sequence_count=parse_int(cfg["tm_seq"]),
            bitrate_bps=parse_int(cfg["tm_bitrate"]),
            space_packet_config=sp_cfg,
        )
        tc_cfg = TCConfig(
            tc_apid=parse_int(cfg["tc_apid"]),
            tc_sequence_count=parse_int(cfg["tc_seq"]),
            bitrate_bps=parse_int(cfg["tc_bitrate"]),
            tfvn=parse_int(cfg["tc_tfvn"]),
            bypass=parse_int(cfg["tc_bypass"]),
            control=parse_int(cfg["tc_control"]),
            scid=parse_int(cfg["tc_scid"]),
            vcid=parse_int(cfg["tc_vcid"]),
            frame_sequence_number=parse_int(cfg["tc_frame_seq"]),
            include_fecf=bool(parse_int(cfg["tc_include_fecf"])),
            space_packet_config=sp_cfg,
        )
        manual_bits = []
        if cfg["manual_tm_bits"]:
            manual_bits = [parse_int(x.strip()) for x in cfg["manual_tm_bits"].replace(";", ",").split(",") if x.strip()]
        return cfg["mission_id"], tm_cfg, tc_cfg, manual_bits, parse_int(cfg["random_tm_count"]), cfg["random_seed"]

    def collect_sensors(self):
        sensors = []
        for row in self.sensor_rows:
            if not row["enabled"].get():
                continue
            sensors.append(Sensor(
                name=row["name"].get().strip(),
                value=parse_float(row["value"].get()),
                unit=row["unit"].get().strip(),
                scale=parse_float(row["scale"].get()),
                parameter_id=parse_int(row["pid"].get()),
            ))
        return sensors

    def collect_commands(self):
        switches = []
        for row in self.switch_rows:
            if not row["enabled"].get():
                continue
            switches.append(SwitchCommand(
                name=row["name"].get().strip(),
                command_id=parse_int(row["id"].get()),
                state_on=(row["state"].get() == "ON"),
            ))
        attitudes = []
        for row in self.attitude_rows:
            if not row["enabled"].get():
                continue
            attitudes.append(AttitudeCommand(
                name=row["name"].get().strip(),
                command_id=parse_int(row["id"].get()),
                x_deg=parse_float(row["x"].get()),
                y_deg=parse_float(row["y"].get()),
                z_deg=parse_float(row["z"].get()),
            ))
        return switches, attitudes

    def run_all(self):
        try:
            mission_id, tm_cfg, tc_cfg, manual_bits, random_count, seed = self.collect_config()
            sensors = self.collect_sensors()
            switches, attitudes = self.collect_commands()

            tm_payload, sensor_explanations = build_tm_sensor_payload(mission_id, sensors)
            tm_packet = build_tm_space_packet(tm_payload, tm_cfg)
            tm_build = build_tm_cadu(tm_packet, tm_cfg)

            rng = random.Random(None if seed == "" else parse_int(seed))
            random_bits = [rng.randrange(0, len(tm_build["randomized"]) * 8) for _ in range(random_count)]
            bit_positions = manual_bits + random_bits
            broken_randomized, events = flip_bits(tm_build["randomized"], bit_positions)
            broken_cadu = ASM + broken_randomized
            tm_rx = receive_tm_cadu(broken_cadu, len(tm_packet), tm_cfg)

            tc_payload, command_explanations = build_tc_command_payload(mission_id, switches, attitudes)
            tc_packet = build_tc_space_packet(tc_payload, tc_cfg)
            tc_frame = build_tc_transfer_frame(tc_packet, tc_cfg)

            self._set_text(self.txt_tm, self.tm_text(mission_id, tm_cfg, tm_payload, sensor_explanations, tm_packet, tm_build, events, random_bits, tm_rx))
            self._set_text(self.txt_rs, self.rs_text(tm_rx))
            self._set_text(self.txt_tc, self.tc_text(mission_id, tc_cfg, tc_payload, command_explanations, tc_packet, tc_frame))
            self._set_text(self.txt_bits, self.bits_text(tm_cfg, tc_cfg, events, bit_positions, tm_build, tc_frame))

            self.last_report = {
                "mission_id": mission_id,
                "tm_space_packet_hex": hex_bytes(tm_packet),
                "tm_cadu_hex": hex_bytes(tm_build["cadu"]),
                "tc_space_packet_hex": hex_bytes(tc_packet),
                "tc_transfer_frame_hex": hex_bytes(tc_frame["frame"]),
                "tm_bit_errors": bit_positions,
                "tm_rs_passed": tm_rx["passed"],
                "tc_fecf_valid": tc_frame["fecf_valid"],
            }
            self.nb.select(self.tab_tm_output)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def tm_text(self, mission_id, cfg, payload, sensor_explanations, packet, build, events, random_bits, rx):
        hdr = parse_space_packet_header(packet)
        L = []
        L.append("FULL TM BUILD: USER SENSOR DATA -> SPACE PACKET -> RS I=5 -> RANDOMIZER -> ASM/CADU")
        L.append("=" * 120)
        L.append("0. Visible configuration")
        L.append(f"   Mission ID text in Packet Data Field = {mission_id!r}")
        L.append(f"   TM APID = {cfg.tm_apid}, TM Sequence Count = {cfg.tm_sequence_count}, bitrate = {cfg.bitrate_bps} bps")
        L.append(f"   RS: J={J}, E={E}, n={RS_N}, k={RS_K}, parity={RS_PARITY}, interleaving I={cfg.interleaving_depth}")
        L.append(f"   ASM = {hex_bytes(ASM)}, fill byte = 0x{cfg.fill_byte:02X}")
        L.append("")
        L.append("1. TM sensor payload")
        L.append(f"   Payload length = {len(payload)} bytes")
        L.append(f"   Payload hex = {hex_bytes(payload)}")
        for line in sensor_explanations:
            L.append(f"   {line}")
        L.append("")
        L.append("2. TM Space Packet")
        L.append(f"   Space Packet length = {len(packet)} bytes")
        L.append(f"   Space Packet hex = {hex_bytes(packet)}")
        L.append(f"   Header: PVN={hdr.pvn}, Type={hdr.packet_type}, APID={hdr.apid}, SeqFlags={hdr.sequence_flags}, SeqCount={hdr.sequence_count}, DataLength={hdr.packet_data_length}")
        L.append("")
        L.append("3. RS interleaving and codeblock")
        L.append(f"   Data space = k*I = {RS_K}*{cfg.interleaving_depth} = {len(build['data_space'])} bytes")
        L.append(f"   Fill length = {len(build['data_space']) - len(packet)} bytes")
        L.append(f"   Check symbols = 2E*I = {RS_PARITY}*{cfg.interleaving_depth} = {len(build['check'])} bytes")
        L.append(f"   Transmitted codeblock = {len(build['codeblock'])} bytes")
        for i, cw in enumerate(build["codewords"]):
            L.append(f"   RS codeword {i}: 223 data + 32 parity = {len(cw)} bytes; parity first 8 = {hex_bytes(cw[RS_K:RS_K+8])}")
        L.append("")
        L.append("4. Randomizer and CADU")
        L.append("   randomized_bit_i = codeblock_bit_i XOR PN_i")
        L.append(f"   CADU = ASM + randomized codeblock = {len(ASM)} + {len(build['randomized'])} = {len(build['cadu'])} bytes")
        L.append(f"   CADU bits = {len(build['cadu']) * 8}; TX time = {len(build['cadu']) * 8 / cfg.bitrate_bps:.6f} s")
        L.append("")
        L.append("5. Injected TM bit errors")
        if random_bits:
            L.append(f"   Random-selected bit positions = {random_bits}")
        if not events:
            L.append("   No errors injected")
        for bit, byte_i, bit_i, mask, before, after in events:
            L.append(f"   bit {bit}: codeblock byte[{byte_i}], bit_inside_byte={bit_i}, mask=0x{mask:02X}, {bit_marker(before, bit_i)} -> {bit_marker(after, bit_i)}")
        L.append("")
        L.append("6. Receiver result")
        L.append("   Receiver path: ASM search -> derandomize -> deinterleave -> RS decode each codeword")
        L.append(f"   RS overall result = {'PASS' if rx['passed'] else 'FAIL'}")
        L.append(f"   Recovered Space Packet hex = {hex_bytes(rx['recovered_packet'])}")
        return "\n".join(L)

    def rs_text(self, rx):
        L = []
        L.append("FULL RS DECODER TRACE")
        L.append("=" * 120)
        L.append("Every RS codeword uses: syndromes -> Berlekamp-Massey -> Chien search -> Forney magnitudes -> XOR correction")
        L.append("")
        for i, report in enumerate(rx.get("reports", [])):
            L.append(f"RS decoder/codeword {i}")
            L.append(f"  Nonzero syndromes before = {report.nonzero_before} of 32")
            L.append(f"  Syndromes before = {hxlst(report.syndromes_before)}")
            L.append(f"  Locator degree = {report.locator_degree}")
            L.append(f"  Locator coefficients = {hxlst(report.locator)}")
            L.append(f"  Chien located byte-symbol positions = {report.positions}")
            L.append(f"  Omega coefficients = {hxlst(report.omega)}")
            L.append(f"  Lambda derivative coefficients = {hxlst(report.derivative)}")
            L.append(f"  Forney magnitudes = {hxlst(report.magnitudes)}")
            for pos, mag in zip(report.positions, report.magnitudes):
                L.append(f"  Correct byte[{pos}] using XOR magnitude 0x{mag:02X}")
            L.append(f"  Syndromes after = {hxlst(report.syndromes_after)}")
            L.append(f"  Syndromes after all zero? {'YES' if report.nonzero_after == 0 else 'NO'}")
            L.append(f"  Result = {'PASS' if report.passed else 'FAIL'}")
            L.append("")
        return "\n".join(L)

    def tc_text(self, mission_id, cfg, payload, command_explanations, packet, frame):
        hdr = parse_space_packet_header(packet)
        L = []
        L.append("FULL TC BUILD: USER COMMANDS -> TC SPACE PACKET -> TC TRANSFER FRAME -> FECF")
        L.append("=" * 120)
        L.append("0. Visible configuration")
        L.append(f"   Mission ID text in Packet Data Field = {mission_id!r}")
        L.append(f"   TC APID = {cfg.tc_apid}, TC Space Packet SeqCount = {cfg.tc_sequence_count}")
        L.append(f"   TFVN={cfg.tfvn}, Bypass={cfg.bypass}, Control={cfg.control}, Spare={cfg.spare}")
        L.append(f"   SCID={cfg.scid} (0x{cfg.scid:03X}), VCID={cfg.vcid}, FrameSeq={cfg.frame_sequence_number}")
        L.append(f"   Include FECF={cfg.include_fecf}, bitrate={cfg.bitrate_bps} bps")
        L.append("   Note: Mission ID text is not SCID. SCID is a numeric 10-bit frame field.")
        L.append("")
        L.append("1. TC command payload")
        L.append(f"   Payload length = {len(payload)} bytes")
        L.append(f"   Payload hex = {hex_bytes(payload)}")
        for line in command_explanations:
            L.append(f"   {line}")
        L.append("")
        L.append("2. TC Space Packet")
        L.append(f"   Packet hex = {hex_bytes(packet)}")
        L.append(f"   Header: PVN={hdr.pvn}, Type={hdr.packet_type}, APID={hdr.apid}, SeqFlags={hdr.sequence_flags}, SeqCount={hdr.sequence_count}, DataLength={hdr.packet_data_length}")
        L.append("")
        L.append("3. TC Transfer Frame")
        L.append(f"   Primary header = {hex_bytes(frame['header'])}")
        L.append("   Header layout: TFVN(2) | Bypass(1) | Ctrl(1) | Spare(2) | SCID(10) | VCID(6) | Length(10) | SeqNo(8)")
        L.append(f"   Frame Length C = total octets - 1 = {len(frame['frame'])} - 1 = {frame['frame_length_c']}")
        L.append(f"   Full frame length = {len(frame['frame'])} bytes")
        L.append(f"   Full frame hex = {hex_bytes(frame['frame'])}")
        if cfg.include_fecf:
            L.append(f"   FECF = {hex_bytes(frame['fecf'])}")
            L.append(f"   Recomputed FECF = {crc16_ccitt(frame['frame_without_fecf']).to_bytes(2, 'big').hex(' ').upper()}")
            L.append(f"   FECF validation = {'PASS' if frame['fecf_valid'] else 'FAIL'}")
        else:
            L.append("   FECF disabled")
        L.append(f"   TC bits = {len(frame['frame']) * 8}; TX time = {len(frame['frame']) * 8 / cfg.bitrate_bps:.6f} s")
        return "\n".join(L)

    def bits_text(self, tm_cfg, tc_cfg, events, bit_positions, tm_build, tc_frame):
        L = []
        L.append("BIT / BYTE / TIMING EXPLANATION")
        L.append("=" * 120)
        L.append("1 byte = 8 bits")
        L.append("byte_index = bit_index // 8")
        L.append("bit_inside_byte = bit_index % 8")
        L.append("")
        if bit_positions:
            L.append("Entered/generated TM bit positions:")
            for bit in bit_positions:
                L.append(f"  bit {bit}: byte_index={bit}//8={bit//8}, bit_inside_byte={bit}%8={bit%8}")
        else:
            L.append("No TM bit errors entered")
        L.append("")
        L.append(f"TM CADU bytes = {len(tm_build['cadu'])}, bits = {len(tm_build['cadu']) * 8}, time @ {tm_cfg.bitrate_bps} bps = {len(tm_build['cadu']) * 8 / tm_cfg.bitrate_bps:.6f} s")
        L.append(f"TC frame bytes = {len(tc_frame['frame'])}, bits = {len(tc_frame['frame']) * 8}, time @ {tc_cfg.bitrate_bps} bps = {len(tc_frame['frame']) * 8 / tc_cfg.bitrate_bps:.6f} s")
        L.append("")
        L.append("TM bit positions are relative to the randomized transmitted codeblock after the ASM is removed.")
        L.append("TC bitstream timing is for the TC Transfer Frame/FECF path. BCH/CLTU is not implemented.")
        return "\n".join(L)

    def constants_text(self):
        return f"""CONSTANTS AND FIELD DEFINITIONS
{"=" * 120}

Generic version rule:
  Full CCSDS path only.

Space Packet:
  PVN = 0 by default
  Secondary Header Flag = 0 by default
  Sequence Flags = 3, binary 11, unsegmented
  APID = user-configurable, 0..2047
  Sequence Count = user-configurable, 0..16383
  Packet Data Length C = Packet Data Field octets - 1

TM RS / sync:
  J = {J}
  E = {E}
  n = 2^J - 1 = {RS_N}
  k = n - 2E = {RS_K}
  parity = 2E = {RS_PARITY}
  correction capability t = E = {RS_T} byte-symbol errors/codeword
  Interleaving depth I = {INTERLEAVING_DEPTH}
  GF polynomial = x^8+x^7+x^2+x+1 = 0x{GF_PRIM_POLY:X}
  Generator roots = alpha^(11j), j={RS_FCR}..{RS_FCR + RS_PARITY - 1}
  ASM = {hex_bytes(ASM)}
  Fill byte = 0x{FILL_BYTE:02X}

TC Transfer Frame:
  Primary Header = 5 octets
  FECF optional = 2 octets
  TFVN 2 bits
  Bypass 1 bit
  Control 1 bit
  Spare 2 bits
  SCID 10 bits, numeric
  VCID 6 bits
  Frame Length 10 bits, C = total transfer-frame octets - 1
  Frame Sequence Number 8 bits
  FECF polynomial G(X)=X^16+X^12+X^5+1 = 0x1021

Mission-defined payload:
  TM sensor payload supports up to {MAX_SENSORS} enabled sensors.
  TC switch payload supports up to {MAX_SWITCH_COMMANDS} switch commands.
  TC attitude payload supports up to {MAX_ATTITUDE_COMMANDS} attitude pointing instructions.
"""

    def save_config(self):
        try:
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not path:
                return
            data = {
                "config": {k: e.get() for k, e in self.cfg_entries.items()},
                "sensors": [
                    {k: (v.get() if hasattr(v, "get") else v) for k, v in {
                        "enabled": row["enabled"].get(), "name": row["name"], "value": row["value"], "unit": row["unit"], "scale": row["scale"], "pid": row["pid"]
                    }.items()}
                    for row in self.sensor_rows
                ],
            }
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def load_config(self):
        messagebox.showinfo(APP_TITLE, "Load configuration is intentionally minimal in this release. Use examples/demo_config.json as reference.")

    def export_report(self):
        try:
            if not self.last_report:
                self.run_all()
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not path:
                return
            Path(path).write_text(json.dumps(self.last_report, indent=2), encoding="utf-8")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))


if __name__ == "__main__":
    App().mainloop()
