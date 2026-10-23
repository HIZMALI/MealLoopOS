"""Descriptive statistics only. Repeated per-diner values are never added as mass."""
import pandas as pd


def optional_sum(series):
    value = series.sum(min_count=1)
    return None if pd.isna(value) else float(value)


def summarize(records):
    frame = pd.DataFrame([{"plate": r.plate_waste_kg, "kitchen": r.kitchen_serving_waste_kg, "diners": r.diners}
                          for r in records], columns=["plate", "kitchen", "diners"], dtype=float)
    complete = frame[frame.plate.notna() & frame.kitchen.notna()]
    eligible = complete[complete.diners.notna() & (complete.diners > 0)]
    plate, kitchen = optional_sum(frame.plate), optional_sum(frame.kitchen)
    all_mass = frame[["plate", "kitchen"]].sum(axis=1, min_count=1)
    return {
        "days": len(frame), "plate_waste_kg": plate, "kitchen_serving_waste_kg": kitchen,
        "combined_recorded_waste_kg": optional_sum(all_mass),
        "complete_waste_kg": optional_sum(complete.plate + complete.kitchen),
        "average_waste_per_diner_g": float((eligible.plate + eligible.kitchen).sum() * 1000 / eligible.diners.sum()) if len(eligible) else None,
        "average_daily_combined_kg": float((complete.plate + complete.kitchen).mean()) if len(complete) else None,
        "average_daily_plate_kg": None if pd.isna(frame.plate.mean()) else float(frame.plate.mean()),
        "average_daily_kitchen_kg": None if pd.isna(frame.kitchen.mean()) else float(frame.kitchen.mean()),
        "diners_recorded": optional_sum(frame.diners),
        "coverage": {"plate_days": int(frame.plate.count()), "kitchen_days": int(frame.kitchen.count()),
            "complete_days": len(complete), "per_diner_days": len(eligible),
            "per_diner_diners": int(eligible.diners.sum())},
    }


def chart_data(records):
    daily = []
    for r in records:
        complete = r.plate_waste_kg is not None and r.kitchen_serving_waste_kg is not None
        combined = r.plate_waste_kg + r.kitchen_serving_waste_kg if complete else None
        daily.append({"day_index": r.day_index, "source_row": r.source_row, "date": str(r.date) if r.date else None,
            "label": str(r.date) if r.date else f"Day {r.day_index}", "phase": r.phase, "menu": r.menu,
            "diners": r.diners, "plate_waste_kg": r.plate_waste_kg, "kitchen_serving_waste_kg": r.kitchen_serving_waste_kg,
            "combined_waste_kg": combined,
            "waste_per_diner_g": combined * 1000 / r.diners if combined is not None and r.diners and r.diners > 0 else None,
            "reported_plate_waste_g": r.reported_plate_waste_g,
            "reported_plate_g_per_diner": r.reported_plate_g_per_diner,
            "reported_kitchen_g_per_diner": r.reported_kitchen_g_per_diner, "issues": r.issues})
    menus = []
    for menu in sorted({r.menu for r in records if r.menu is not None}):
        menus.append({"menu": menu, **summarize([r for r in records if r.menu == menu])})
    return {"daily": daily, "menus": menus, "menu_missing_days": sum(r.menu is None for r in records)}
