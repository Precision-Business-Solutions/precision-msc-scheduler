import streamlit as st
import base64

def render_header(logo_path: str):
    # top white area with logos
    st.markdown(
        """
        <div style="width:100%; display:flex; justify-content:flex-end; padding:8px 0;">
            <img src="data:image/png;base64,{}" style="height:45px;"/>
        </div>
        """.format(_load_image_base64(logo_path)),
        unsafe_allow_html=True
    )

    # blue banner with white title text
    st.markdown(
        """
        <div style="
            width:100%;
            background-color:#5533FF;
            padding:18px;
            border-radius:6px;
            margin-bottom:12px;
        ">
            <h1 style="color:white; margin:0; font-family:'Barlow', sans-serif;">
                Supplier Growth Forum Scheduler
            </h1>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_result_view(toggle_choice, supplier_sched, rep_sched):
    if toggle_choice == "Supplier View":
        selected_supp = st.selectbox(
            "Choose supplier",
            supplier_sched["supplier"].unique()
        )
        st.dataframe(
            supplier_sched[supplier_sched["supplier"] == selected_supp]
        )
        st.button("Print this supplier")
        st.button("Print ALL supplier schedules")

    else:
        selected_rep = st.selectbox(
            "Choose sales rep",
            rep_sched["rep"].unique()
        )
        st.dataframe(
            rep_sched[rep_sched["rep"] == selected_rep]
        )
        st.button("Print this rep")
        st.button("Print ALL rep schedules")



def _load_image_base64(image_path):
    with open(image_path, "rb") as img_f:
        return base64.b64encode(img_f.read()).decode()
