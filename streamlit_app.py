"""Streamlit UI — Personal Finance Coach demo."""
import streamlit as st
import json, time, requests

st.set_page_config(page_title="Personal Finance Coach", layout="wide")
st.title("💰 Personal Finance Coach")

# Sidebar
st.sidebar.header("Settings")
mode = st.sidebar.radio("Architecture", ["crew", "baseline"])
st.sidebar.markdown("---")
st.sidebar.markdown("**crew** = 3 agents (safety + data + advisor)")
st.sidebar.markdown("**baseline** = single agent with all tools")

# Tabs
tab_chat, tab_eval = st.tabs(["💬 Chat", "📊 Eval"])

with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "traces" not in st.session_state:
        st.session_state.traces = []

    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
        if msg["role"] == "assistant" and i // 2 < len(st.session_state.traces):
            trace = st.session_state.traces[i // 2]
            with st.expander(f"🔍 Trace — {trace.get('latency_ms', '?')}ms | tokens: {trace.get('tokens', '?')}"):
                st.json(trace)

    query = st.chat_input("Задай питання про свої фінанси...")

    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("Думаю..."):
                try:
                    resp = requests.post("http://localhost:5000/chat",
                                         json={"query": query, "mode": mode, "session_id": "streamlit"},
                                         timeout=30)
                    data = resp.json()
                    answer = data.get("response", "Помилка")
                    st.write(answer)

                    trace_info = {
                        "mode": data.get("mode"),
                        "latency_ms": data.get("latency_ms"),
                        "tokens": data["usage"]["input_tokens"] + data["usage"]["output_tokens"],
                        "usage": data.get("usage"),
                        "agents": data.get("trace", []),
                    }
                    st.session_state.traces.append(trace_info)
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                    with st.expander(f"🔍 Trace — {trace_info['latency_ms']}ms | {trace_info['tokens']} tokens"):
                        st.json(trace_info)
                except Exception as e:
                    st.error(f"Error: {e}. Make sure Flask API is running (python app.py)")

with tab_eval:
    st.header("Golden Set Evaluation")
    if st.button("🚀 Run Evaluation (both architectures)"):
        with st.spinner("Running 18 test cases on crew & baseline... (this takes ~3 min)"):
            try:
                # Import and run directly (avoid HTTP timeout)
                import sys, os
                sys.path.insert(0, os.path.dirname(__file__))
                from eval.run_eval import run_evaluation
                results = run_evaluation()

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("🤖 Crew (Multi-Agent)")
                    st.json(results["crew_summary"])
                with col2:
                    st.subheader("🔧 Baseline (Single Agent)")
                    st.json(results["baseline_summary"])

                st.markdown("---")
                st.subheader("Detailed Results")
                for i, test in enumerate(results["crew"]):
                    with st.expander(f"{test['id']} — {'✅' if test['evaluation'].get('success') else '❌'}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("**Crew:**")
                            st.write(test["response"])
                            st.caption(f"Latency: {test['latency_ms']}ms")
                        with c2:
                            st.markdown("**Baseline:**")
                            st.write(results["baseline"][i]["response"])
                            st.caption(f"Latency: {results['baseline'][i]['latency_ms']}ms")

                # Save results
                with open("eval/results.json", "w") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                st.success("Results saved to eval/results.json")
            except Exception as e:
                st.error(f"Evaluation error: {e}")

    # Show existing results if available
    try:
        with open("eval/results.json") as f:
            existing = json.load(f)
        st.markdown("---")
        st.subheader("Last Run Results")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Crew Success Rate", f"{existing['crew_summary']['success_rate']:.0%}")
            st.metric("Crew Latency P50", f"{existing['crew_summary']['latency_p50']}ms")
        with col2:
            st.metric("Baseline Success Rate", f"{existing['baseline_summary']['success_rate']:.0%}")
            st.metric("Baseline Latency P50", f"{existing['baseline_summary']['latency_p50']}ms")
    except FileNotFoundError:
        st.info("No previous evaluation results. Click 'Run Evaluation' above.")
