import streamlit as st
import pandas as pd
import io

from app.layout import render_header
from app.parsers import parse_meeting_organizer
from app.scheduler import run_scheduler
from app.html_renderer import (
    render_supplier_html,
    render_rep_html,
    build_combined_html,
    render_request_summary_table
)

def attach_substitutions(supplier_sched, supplier_summary):
    """
    Add a 'substitutions' column to supplier_sched by mapping:
    (supplier, request_name) -> list of unavailable reps
    """
    subs_map = {}
    for supp, summary in supplier_summary.items():
        subs = summary.get("substitutions", {})
        for req_name, subs_list in subs.items():
            subs_map[(supp, req_name)] = ", ".join(subs_list)

    supplier_sched = supplier_sched.copy()
    supplier_sched["substitutions"] = supplier_sched.apply(
        lambda r: subs_map.get((r["supplier"], r["category"]), ""),
        axis=1
    )
    return supplier_sched


def create_download_workbook(supplier_sched, rep_sched, supplier_summary):
    """
    Build a formatted Excel workbook with:
    - Suppliers sheet (with substitutions)
    - Representatives sheet
    """

    output = io.BytesIO()

    # Merge substitutions into supplier schedule
    supplier_sched2 = attach_substitutions(supplier_sched, supplier_summary)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        # Write raw sheets
        supplier_sched2.to_excel(writer, sheet_name="Suppliers", index=False)
        rep_sched.to_excel(writer, sheet_name="Representatives", index=False)

        # Workbook + worksheets
        wb = writer.book
        ws_sup = writer.sheets["Suppliers"]
        ws_rep = writer.sheets["Representatives"]

        # -----------------------------
        # STYLES
        # -----------------------------
        header_fmt = wb.add_format({
            "bold": True,
            "font_name": "Barlow",
            "font_size": 12,
            "align": "left",
            "valign": "vcenter",
            "font_color": "white",
            "bg_color": "#5533FF",
            "border": 1
        })

        cell_fmt = wb.add_format({
            "font_name": "Barlow",
            "font_size": 12,
            "align": "left",
            "valign": "vcenter",
            "border": 1
        })

        money_fmt = wb.add_format({
            "font_name": "Barlow",
            "font_size": 12,
            "align": "right",
            "valign": "vcenter",
            "border": 1,
            "num_format": "$#,##0"
        })

        # SUPPLIERS SHEET
        sup_df = supplier_sched2

        for col_idx, col_name in enumerate(sup_df.columns):

            # Write header
            ws_sup.write(0, col_idx, col_name, header_fmt)

            is_money = col_name in ["total_opportunity", "opportunity"]

            for row_idx in range(1, len(sup_df) + 1):

                val = sup_df.iloc[row_idx - 1, col_idx]

                # --- Fix list types ---
                if isinstance(val, list):
                    val = ", ".join([str(x) for x in val])

                # --- Clean NaN ---
                if pd.isna(val):
                    val = ""

                # --- Apply formatting ---
                if is_money:
                    try:
                        ws_sup.write_number(row_idx, col_idx, float(val), money_fmt)
                    except:
                        ws_sup.write(row_idx, col_idx, "", money_fmt)
                else:
                    ws_sup.write(row_idx, col_idx, val, cell_fmt)

            # Auto width
            max_width = max(
                len(str(col_name)),
                sup_df[col_name].astype(str).map(len).max()
            )
            ws_sup.set_column(col_idx, col_idx, min(max_width + 2, 40))

        # REPRESENTATIVES SHEET
        rep_df = rep_sched

        for col_idx, col_name in enumerate(rep_df.columns):

            ws_rep.write(0, col_idx, col_name, header_fmt)

            for row_idx in range(1, len(rep_df) + 1):

                val = rep_df.iloc[row_idx - 1, col_idx]

                if isinstance(val, list):
                    val = ", ".join([str(x) for x in val])

                if pd.isna(val):
                    val = ""

                ws_rep.write(row_idx, col_idx, val, cell_fmt)

            max_width = max(
                len(str(col_name)),
                rep_df[col_name].astype(str).map(len).max()
            )
            ws_rep.set_column(col_idx, col_idx, min(max_width + 2, 40))

    return output.getvalue()




def main():
    st.set_page_config(page_title="Supplier Growth Forum Scheduler", layout="wide")
    render_header("files/logos.png")

    # -------------------------------------------------------------------
    # Instructions
    # -------------------------------------------------------------------
    st.markdown(
    """
        #### How to Use This Tool
        This application generates schedules for all Suppliers and attending MSC Sales Representatives for the Supplier Growth Forum.

        1. Upload the Meeting Organizer Excel file  
        2. Set the meeting limits  
        3. Run the scheduler  
        4. View Supplier or Sales Rep calendars  
        5. Export single or combined PDFs 

        #### Source Data and Definitions

        Supplier type and opportunity data come from the Supplier Growth Forum model outputs.  
        The list of attending Sales Representatives comes from the MSC invite list from Leah Bacon updated on Jan. 6, 2026.  
        Supplier meeting requests come from the Meeting Tracker and include each supplier's meeting number, topic, and preferred attendee type or region.

        Request cleaning follows these principles:  
        - Use explicit region or name requests when provided  
        - If a request references a sector or vertical, assign the reps most aligned with opportunity  
        - When unclear, assign the region with the greatest modeled opportunity for that supplier  

        #### Scheduling Algorithm

        The scheduler first interprets each request into the actual reps who should attend.  
        Region requests are expanded into Key Leaders, Region Leaders, and District Leaders depending on whether the supplier is Peak or Accelerating.  
        Name requests use the reps exactly as listed.

        Next, workloads are balanced so no rep is assigned to more meetings than allowed.  
        When a rep appears too often, controlled substitutions are made:  
        - Key Leaders may be replaced with Region or District Leaders in the same segment  
        - Region Leaders may be replaced with District Leaders in the same region  
        - District Leaders may be swapped with another District Leader in the same region Reps that cannot be replaced are removed and marked as unavailable.

        Finally, suppliers are scheduled with Peak suppliers placed first, then Accelerating.  
        Meetings are attempted in priority order and placed only when all reps are available, the supplier is free, and no workload limits are exceeded.  
        Multiple internal configurations are tested automatically, and the solution with the fewest unscheduled meetings is returned.

        All processing happens locally in your browser session. 

        #### Support
        For questions or assistance, contact **Precision Business Solutions**  
        """
    )

    # -------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------
    st.subheader("Scheduler Settings")

    colA, colB, colC = st.columns(3)
    with colA:
        max_meetings_rep = st.number_input("Max meetings per rep", 1, 50, 12)
    with colB:
        max_peak = st.number_input("Meetings per Peak supplier", 1, 50, 6)
    with colC:
        max_acc = st.number_input("Meetings per Accelerating supplier", 1, 50, 3)

    # -------------------------------------------------------------------
    # Upload
    # -------------------------------------------------------------------
    uploaded = st.file_uploader(
        "Upload Excel File (Meeting Requests + Sales Reps)",
        type=["xlsx"]
    )
    if not uploaded:
        return

    suppliers_df, reps_df, preferences = parse_meeting_organizer(uploaded)

    # -------------------------------------------------------------------
    # Run scheduler
    # -------------------------------------------------------------------
    if st.button("Run Scheduler"):
        with st.spinner("Generating schedules… this may take a moment."):
            supplier_sched, rep_sched, supplier_summary, validation = run_scheduler(
                preferences,
                reps_df,
                max_meetings_rep,
                max_peak,
                max_acc,
                seeds=25
            )

            st.session_state["supplier_sched"] = supplier_sched
            st.session_state["rep_sched"] = rep_sched
            st.session_state["supplier_summary"] = supplier_summary
            st.session_state["validation"] = validation

            # Validate all suppliers present
            missing = [
                s for s in suppliers_df["Supplier"]
                if s not in supplier_summary
            ]

        # show warnings *after* spinner closes
        if missing:
            st.warning(f"Warning: The following suppliers did not appear in schedule results: {missing}")

        st.success("Schedule generated successfully!")

    # Stop if not run yet
    if "supplier_sched" not in st.session_state:
        return

    supplier_sched = st.session_state["supplier_sched"]
    rep_sched = st.session_state["rep_sched"]
    supplier_summary = st.session_state["supplier_summary"]

    # -------------------------------------------------------------------
    # Tabs
    # -------------------------------------------------------------------
    tab_suppliers, tab_reps, tab_download = st.tabs(["Supplier View", "Sales Rep View", "Download"])

    # ============================================================
    # SUPPLIER TAB
    # ============================================================
    with tab_suppliers:
        col_select, spacer, col_btn = st.columns([2, 2, 1])

        with col_select:
            selected_supplier = st.selectbox(
                "Select Supplier",
                suppliers_df["Supplier"].tolist(),
                key="supplier_select"
            )

        with col_btn:
            if st.button("Save ALL Supplier Schedules (PDF)"):

                pages = []
                for supp in suppliers_df["Supplier"]:
                    booth_s = suppliers_df.loc[
                        suppliers_df["Supplier"] == supp,
                        "Booth"
                    ].iloc[0]

                    df_s = supplier_sched[supplier_sched["supplier"] == supp]
                    summary_s = supplier_summary.get(supp, {})

                    pages.append(
                        render_supplier_html(supp, booth_s, df_s, summary_s, reps_df)
                    )

                big_html = build_combined_html(pages)

                st.components.v1.html(
                    f"""
                    <iframe id="print_all_suppliers" style="display:none;"></iframe>
                    <script>
                        const iframe = document.getElementById("print_all_suppliers");
                        const doc = iframe.contentWindow.document;
                        doc.open();
                        doc.write(`{big_html.replace("`", "\\`")}`);
                        doc.close();
                        setTimeout(() => iframe.contentWindow.print(), 300);
                    </script>
                    """,
                    height=0
                )

        # Render selected supplier
        booth_val = suppliers_df.loc[
            suppliers_df["Supplier"] == selected_supplier,
            "Booth"
        ].iloc[0]

        df_supplier = supplier_sched[supplier_sched["supplier"] == selected_supplier]
        html_supplier = render_supplier_html(
            selected_supplier,
            booth_val,
            df_supplier,
            supplier_summary[selected_supplier],
            reps_df
        )
        st.components.v1.html(html_supplier, height=950, scrolling=True)

        # Request summary table
        summary_html_block = render_request_summary_table(
            supplier_summary[selected_supplier]
        )
        st.components.v1.html(summary_html_block, height=400, scrolling=True)


    # ============================================================
    # REP TAB
    # ============================================================
    with tab_reps:

        meeting_reps = sorted(rep_sched["rep"].unique().tolist())

        col_select, spacer, col_btn = st.columns([2, 2, 1])

        with col_select:
            selected_rep = st.selectbox(
                "Select Sales Rep",
                meeting_reps,
                key="rep_select"
            )

        with col_btn:
            if st.button("Save ALL Rep Schedules (PDF)"):

                pages = []
                for rep in meeting_reps:
                    df_rep = rep_sched[rep_sched["rep"] == rep]
                    pages.append(
                        render_rep_html(rep, df_rep, suppliers_df, reps_df)
                    )

                big_html = build_combined_html(pages)

                st.components.v1.html(
                    f"""
                    <iframe id="print_all_reps" style="display:none;"></iframe>
                    <script>
                        const iframe = document.getElementById("print_all_reps");
                        const doc = iframe.contentWindow.document;
                        doc.open();
                        doc.write(`{big_html.replace("`", "\\`")}`);
                        doc.close();
                        setTimeout(() => iframe.contentWindow.print(), 300);
                    </script>
                    """,
                    height=0
                )

        df_rep_selected = rep_sched[rep_sched["rep"] == selected_rep]
        html_rep = render_rep_html(selected_rep, df_rep_selected, suppliers_df, reps_df)
        st.components.v1.html(html_rep, height=1100, scrolling=True)
    
    # ============================================================
    # DOWNLOAD TAB
    # ============================================================
    with tab_download:
        st.subheader("Download Raw Schedule Outputs")

        st.markdown("""
        This export includes:
        - **Suppliers**: the full supplier meeting schedule  
        - **Representatives**: the full sales rep meeting schedule  
        """)

        # Build Excel when requested
        excel_bytes = create_download_workbook(
            supplier_sched,
            rep_sched,
            supplier_summary
        )

        st.download_button(
            label="Download Scheduler Output (Excel)",
            data=excel_bytes,
            file_name="SGF_Schedule_Output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )




if __name__ == "__main__":
    main()
