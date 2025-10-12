# This code was adapted from https://github.com/MarvinIRW/Assessing-Answer-Accuracy-Hallucination-and-Document-Relevance-in-virtUOS-Chatbot/tree/main/code/eval

import os

import pandas as pd
from bert_score import score


def compute_bertscore(
    df: pd.DataFrame,
    reference_col: str,
    hypothesis_col: str,
    question_id_col: str,
    language: str,
    output_csv_path: str,
    mean_csv_path=None,
) -> pd.DataFrame:
    """
    Computes BERTScore for each row in `df`.
    """
    references = df[reference_col].astype(str).tolist()
    hypotheses = df[hypothesis_col].astype(str).tolist()
    assert len(references) == len(
        hypotheses
    ), "Mismatch in # of references vs. hypotheses"

    (P, R, F1), bert_hash = score(
        cands=hypotheses, refs=references, lang=language, verbose=True, return_hash=True
    )

    bert_df = pd.DataFrame(
        {
            question_id_col: df[question_id_col].values,
            "BERTScore_P": P.tolist(),
            "BERTScore_R": R.tolist(),
            "BERTScore_F1": F1.tolist(),
        }
    )

    system_f1_mean = bert_df["BERTScore_F1"].mean()
    print(f"[{language.upper()}] System-level BERTScore F1: {system_f1_mean:.3f}")
    print(f"[{language.upper()}] BERTScore hash code: {bert_hash}\n")

    bert_df.to_csv(output_csv_path, index=False, quoting=1)
    print(f"BERTScore results saved to: {output_csv_path}")

    if (
        mean_csv_path is not None
        and os.path.exists(mean_csv_path)
        and language is not None
    ):
        mean_eval = pd.read_csv(mean_csv_path)
        metric_name = f"BERTScore_F1_{language}"
        if metric_name not in mean_eval["metric"].values:
            mean_eval = pd.concat(
                [
                    mean_eval,
                    pd.DataFrame([{"metric": metric_name, "value": system_f1_mean}]),
                ],
                ignore_index=True,
            )
        mean_eval.to_csv(mean_csv_path, index=False)

    return bert_df


def run_bertscore_eval(config):
    csv_path_de = config.get("csv_path_de")
    mean_csv_path = config.get("csv_path_mean_bert", None)
    output_csv_de = config.get("output_csv_bert", None)
    if not csv_path_de or not output_csv_de:
        raise ValueError("csv_path_de and output_csv_bert must be set in config.")

    df_de = pd.read_csv(csv_path_de)
    bert_df_de = compute_bertscore(
        df=df_de,
        reference_col="human_answer",
        hypothesis_col="chatbot_answer",
        question_id_col="question_id_q",
        language="de",
        output_csv_path=output_csv_de,
        mean_csv_path=mean_csv_path,
    )
    return bert_df_de
