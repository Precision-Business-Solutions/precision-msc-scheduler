import pandas as pd
import random
from app.utils import time_slots


def resolve_request(request, reps_df):
    '''Interpret a supplier request into a rep candidate list'''
    req = str(request).strip()

    # 1. exact rep name
    exact = reps_df[reps_df["Sales Rep."] == req]
    if len(exact) > 0:
        return exact.copy(), "rep"

    # 2. subcategory exact match
    sub = reps_df[reps_df["Subcategory"] == req]
    if len(sub) > 0:
        return sub.sort_values("Subcat Rank").copy(), "subcat"

    # 3. category exact match
    cat = reps_df[reps_df["Category"] == req]
    if len(cat) > 0:
        return cat.sort_values("Cat Rank").copy(), "category"

    return pd.DataFrame(), "none"


def request_specificity(req_list, reps_df):
    '''Determine specificity score (rep < subcat < cat < none)'''
    best = 3
    for req in req_list:
        _, rtype = resolve_request(req, reps_df)
        if rtype == "rep":
            return 0
        if rtype == "subcat":
            best = min(best, 1)
        if rtype == "category":
            best = min(best, 2)
    return best


def build_random_timeslot_order():
    '''
    Build a randomized list of all available timeslots per supplier.
    Avoids same day clustering.
    '''
    all_slots = []
    for day, slots in time_slots.items():
        for slot, state in slots.items():
            if state not in ("LUNCH", "BREAK"):
                all_slots.append((day, slot))

    random.shuffle(all_slots)
    return all_slots



def find_randomized_slot(supplier, rep, supplier_rows, rep_avail, randomized_slots):
    supplier_used = {
        (row["day"], row["timeslot"])
        for row in supplier_rows
        if row["supplier"] == supplier
    }

    for (day, slot) in randomized_slots:

        if (day, slot) in supplier_used:
            continue

        if rep_avail[rep][day][slot] is True:
            return day, slot

    return None, None


# ----------------------------------------------------------
#                     MAIN SCHEDULER 
# ----------------------------------------------------------
def run_scheduler(
        suppliers_df,
        reps_df,
        preferences,
        max_meetings_rep,
        max_peak,
        max_acc
    ):

    # build rep availability
    rep_avail = {
        rep: {
            day: {slot: (blocked is None) for slot, blocked in slot_map.items()}
            for day, slot_map in time_slots.items()
        }
        for rep in reps_df["Sales Rep."]
    }

    rep_meeting_count = {rep: 0 for rep in reps_df["Sales Rep."]}
    supplier_meeting_count = {}

    supplier_rows = []
    rep_rows = []
    supplier_summary = {}

    # compute request specificity
    suppliers_df = suppliers_df.copy()
    suppliers_df["Specificity"] = suppliers_df["Supplier"].apply(
        lambda s: request_specificity(preferences[s], reps_df)
    )

    # order suppliers
    ordered_suppliers = suppliers_df.sort_values(
        by=["Type", "Specificity"],
        key=lambda col: (
            col.map({"Peak": 0, "Accelerating": 1})
            if col.name == "Type"
            else col
        )
    )

    # ------------------------------------------------------
    # NEW: Build randomized slot order ONCE PER SUPPLIER
    # ------------------------------------------------------

    randomized_slot_map = {
        supp["Supplier"]: build_random_timeslot_order()
        for _, supp in ordered_suppliers.iterrows()
    }

    # ------------------------------------------------------
    # Begin scheduling
    # ------------------------------------------------------
    for _, supp in ordered_suppliers.iterrows():

        supplier = supp["Supplier"]
        booth = supp["Booth #"]
        s_type = supp["Type"]

        cap = max_peak if s_type == "Peak" else max_acc
        supplier_meeting_count[supplier] = 0

        req_list = preferences[supplier]

        supplier_summary[supplier] = {
            "requested": req_list,
            "fulfilled": [],
            "category_counts": {}
        }

        slot_order = randomized_slot_map[supplier]

        # iterate in request order
        for request in req_list:

            if supplier_meeting_count[supplier] >= cap:
                break

            rep_candidates, req_type = resolve_request(request, reps_df)
            if rep_candidates.empty:
                continue

            assigned_rep = None
            chosen_day = None
            chosen_slot = None
            category_label = None

            # try each candidate rep
            for _, rep_row in rep_candidates.iterrows():

                rep = rep_row["Sales Rep."]

                if rep_meeting_count[rep] >= max_meetings_rep:
                    continue

                day, slot = find_randomized_slot(
                    supplier,
                    rep,
                    supplier_rows,
                    rep_avail,
                    slot_order
                )

                if day and slot:
                    assigned_rep = rep
                    chosen_day = day
                    chosen_slot = slot
                    break

            if assigned_rep:
                # figure category label
                if req_type == "rep":
                    category_label = rep_row["Category"]
                elif req_type == "subcat":
                    category_label = rep_row["Subcategory"]
                elif req_type == "category":
                    category_label = rep_row["Category"]
                else:
                    category_label = request

                supplier_rows.append({
                    "supplier": supplier,
                    "booth": booth,
                    "day": chosen_day,
                    "timeslot": chosen_slot,
                    "rep": assigned_rep,
                    "category": category_label
                })

                rep_rows.append({
                    "rep": assigned_rep,
                    "day": chosen_day,
                    "timeslot": chosen_slot,
                    "supplier": supplier,
                    "booth": booth,
                    "category": category_label
                })

                rep_avail[assigned_rep][chosen_day][chosen_slot] = False
                rep_meeting_count[assigned_rep] += 1
                supplier_meeting_count[supplier] += 1

                supplier_summary[supplier]["fulfilled"].append(request)
                supplier_summary[supplier]["category_counts"][request] = (
                    supplier_summary[supplier]["category_counts"].get(request, 0) + 1
                )

        supplier_summary[supplier]["fulfilled"] = list(
            set(supplier_summary[supplier]["fulfilled"])
        )

    return (
        pd.DataFrame(supplier_rows).sort_values(["supplier", "day", "timeslot"]),
        pd.DataFrame(rep_rows).sort_values(["rep", "day", "timeslot"]),
        supplier_summary
    )
