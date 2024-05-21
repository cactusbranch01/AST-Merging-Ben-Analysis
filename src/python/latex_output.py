#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Output LaTeX tables and plots.

usage: python3 latex_output.py
                --full_repos_csv <path_to_full_repos_csv>
                --repos_head_passes_csv <path_to_repos_head_passes_csv>
                --n_merges <number_of_merges>
                --tested_merges_path <path_to_tested_merges>
                --merges_path <path_to_merges>
                --output_dir <path_to_output>


This script generates all the tables and plots for the paper. It requires the
following input files:
- full_repos_csv: csv file containing the full list of repositories
- repos_head_passes_csv: csv file containing the list of repositories whose head passes tests
- tested_merges_path: path to the directory containing the merge results
- merges_path: path to the directory containing all found merges.
- output_dir: path to the directory where the LaTeX files will be saved
"""

import os
import argparse
from pathlib import Path
import warnings
from typing import List
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
from prettytable import PrettyTable
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TextColumn,
)
import seaborn as sns

from variables import TIMEOUT_TESTING_PARENT, TIMEOUT_TESTING_MERGE
from repo import MERGE_STATE, TEST_STATE, MERGE_TOOL
from loguru import logger

matplotlib.use("pgf")
matplotlib.rcParams.update(
    {
        "pgf.texsystem": "pdflatex",
        "font.family": "serif",
        "text.usetex": True,
        "pgf.rcfonts": False,
    }
)

MERGE_TOOL_RENAME = {
    "gitmerge_ort_adjacent": "Adjacent+ort",
    "gitmerge_ort_imports": "Imports+ort",
    "gitmerge_ort_imports_ignorespace": "Imports+ort-ignorespace",
    "intellimerge": "IntelliMerge",
    "git_hires_merge": "Hires-Merge",
}


def check_fingerprint_consistency(result_df: pd.DataFrame, merge_tools: List[str]):
    """Check if the fingerprints are consistent.

    Args:
        result_df: DataFrame containing the results of the merge tools
        merge_tools: list of merge tools
    """
    for merge_tool1 in merge_tools:
        for merge_tool2 in merge_tools:
            if merge_tool1 == "gitmerge_resolve" or merge_tool2 == "gitmerge_resolve":
                continue
            # ignore adajcent
            if (
                merge_tool1 == "gitmerge_ort_adjacent"
                or merge_tool2 == "gitmerge_ort_adjacent"
            ):
                continue
            # Ignore
            if (
                merge_tool1 == "gitmerge_ort_imports"
                or merge_tool2 == "gitmerge_ort_imports"
            ):
                continue
            if (
                merge_tool1 == "gitmerge_ort_imports_ignorespace"
                or merge_tool2 == "gitmerge_ort_imports_ignorespace"
            ):
                continue
            if merge_tool1 != merge_tool2:
                # Check if fingerprints are the same
                same_fingerprint_mask = (
                    result_df[merge_tool1 + "_merge_fingerprint"]
                    == result_df[merge_tool2 + "_merge_fingerprint"]
                )

                # Check if results are the same
                same_result_mask = result_df[merge_tool1] == result_df[merge_tool2]

                # Check if the fingerprints are the same but the results are different
                inconsistent_mask = same_fingerprint_mask & ~same_result_mask
                if inconsistent_mask.sum() > 0:
                    logger.error(
                        f"Inconsistency found between {merge_tool1} and {merge_tool2} in {inconsistent_mask.sum()} cases."
                    )
                    logger.error(
                        result_df.loc[inconsistent_mask][
                            [
                                merge_tool1,
                                merge_tool2,
                                merge_tool1 + "_merge_fingerprint",
                            ]
                        ]
                    )
                assert (
                    inconsistent_mask.sum() == 0
                ), f"Inconsistency found between {merge_tool1} and {merge_tool2} in {inconsistent_mask.sum()} cases."


def merge_tool_latex_name(name: str) -> str:
    """Return the LaTeX name of a merge tool.
    Args:
        name: name of the merge tool
    Returns:
        LaTeX name of the merge tool
    """
    if name in MERGE_TOOL_RENAME:
        return MERGE_TOOL_RENAME[name]
    name = name.capitalize()
    name = name.replace("_", "-")
    return name.capitalize()


def latex_def(name, value) -> str:
    """Return a LaTeX definition.
    Args:
        name: name of the definition
        value: value of the definition
    Returns:
        LaTeX definition
    """
    return "\\def\\" + name + "{" + str(value) + "\\xspace}\n"


# Dictonary that lists the different subsets of merge tools for which plots
# and tables are generated. The key is the directory name which will contain all figures
# that will be used and the value is the list of plots to contain.
PLOTS = {
    "all": [merge_tool.name for merge_tool in MERGE_TOOL],
    "git": [
        "gitmerge_ort",
        "gitmerge_ort_ignorespace",
        "gitmerge_recursive_histogram",
        "gitmerge_recursive_ignorespace",
        "gitmerge_recursive_minimal",
        "gitmerge_recursive_myers",
        "gitmerge_recursive_patience",
        "gitmerge_resolve",
    ],
    "tools": [
        "gitmerge_ort",
        "gitmerge_ort_ignorespace",
        "gitmerge_ort_adjacent",
        "gitmerge_ort_imports",
        "gitmerge_ort_imports_ignorespace",
        "git_hires_merge",
        "spork",
        "intellimerge",
    ],
}

MERGE_CORRECT_NAMES = [
    TEST_STATE.Tests_passed.name,
]

MERGE_INCORRECT_NAMES = [
    TEST_STATE.Tests_failed.name,
    TEST_STATE.Tests_timedout.name,
]

MERGE_UNHANDLED_NAMES = [
    MERGE_STATE.Merge_failed.name,
    MERGE_STATE.Merge_timedout.name,
]

UNDESIRABLE_STATES = [
    TEST_STATE.Git_checkout_failed.name,
    TEST_STATE.Not_tested.name,
    MERGE_STATE.Git_checkout_failed.name,
    MERGE_STATE.Merge_timedout.name,
]


main_branch_names = ["main", "refs/heads/main", "master", "refs/heads/master"]


def build_table1(
    result_df: pd.DataFrame,
    merge_tools: List[str],
    correct: List[int],
    unhandled: List[int],
    incorrect: List[int],
) -> str:
    """Build a table with the results of the merge tools.
    Args:
        result_df: DataFrame containing the results of the merge tools
        merge_tools: list of merge tools
        correct: list of correct merges
        unhandled: list of unhandled merges
        incorrect: list of incorrect merges
    Returns:
        LaTeX table with the results of the merge tools
    """
    # Table overall results
    table = """% Do not edit.  This file is automatically generated.
\\begin{tabular}{l|c c|c c|c c}
        Tool &
        \\multicolumn{2}{c|}{Correct Merges} &
        \\multicolumn{2}{c|}{Unhandled Merges} &
        \\multicolumn{2}{c}{Incorrect Merges} \\\\
        & \\# & \\% & \\# & \\% & \\# & \\% \\\\
        \\hline\n"""
    total = len(result_df)
    for merge_tool_idx, merge_tool in enumerate(merge_tools):
        correct_percentage = 100 * correct[merge_tool_idx] / total if total != 0 else 0
        unhandled_percentage = (
            100 * unhandled[merge_tool_idx] / total if total != 0 else 0
        )
        incorrect_percentage = (
            100 * incorrect[merge_tool_idx] / total if total != 0 else 0
        )
        table += f"{merge_tool_latex_name(merge_tool):32}"
        table += f" & {correct[merge_tool_idx]:5} & {round(correct_percentage):3}\\%"
        table += (
            f" & {unhandled[merge_tool_idx]:5} & {round(unhandled_percentage):3}\\%"
        )
        table += f" & {incorrect[merge_tool_idx]:5} & {round(incorrect_percentage):3}\\% \\\\\n"
    table += "\\end{tabular}\n"
    return table


def build_table2(main: pd.DataFrame, merge_tools: List[str], feature) -> str:
    """Build a table with the results of the merge tools.
    Args:
        main: DataFrame containing the results of the merge tools for the main branch
        merge_tools: list of merge tools
        feature: DataFrame containing the results of the merge tools for the other branches
    Returns:
        LaTeX table with the results of the merge tools
    """
    table2 = """% Do not edit.  This file is automatically generated.
\\begin{tabular}{c|c c c c|c c c c|c c c c}
            Tool &
            \\multicolumn{4}{c|}{Correct Merges} &
            \\multicolumn{4}{c|}{Unhandled Merges} &
            \\multicolumn{4}{c}{Incorrect Merges} \\\\
            &
            \\multicolumn{2}{c}{Main Branch} &
            \\multicolumn{2}{c|}{Other Branches} &
            \\multicolumn{2}{c}{Main Branch} &
            \\multicolumn{2}{c|}{Other Branches} &
            \\multicolumn{2}{c}{Main Branch} &
            \\multicolumn{2}{c}{Other Branches} \\\\
            \\hline
            & \\# & \\% & \\# & \\% & \\# & \\% & \\# & \\% & \\# & \\% & \\# & \\% \\\\\n"""

    for _, merge_tool in enumerate(merge_tools):
        merge_main = main[merge_tool]
        merge_feature = feature[merge_tool]

        correct_main = sum(val in MERGE_CORRECT_NAMES for val in merge_main)
        correct_main_percentage = (
            100 * correct_main / len(main) if len(main) != 0 else 0
        )
        correct_feature = sum(val in MERGE_CORRECT_NAMES for val in merge_feature)
        correct_feature_percentage = (
            100 * correct_feature / len(feature) if len(feature) > 0 else -1
        )

        incorrect_main = sum(val in MERGE_INCORRECT_NAMES for val in merge_main)
        incorrect_main_percentage = (
            100 * incorrect_main / len(main) if len(main) != 0 else 0
        )
        incorrect_feature = sum(val in MERGE_INCORRECT_NAMES for val in merge_feature)
        incorrect_feature_percentage = (
            100 * incorrect_feature / len(feature) if len(feature) > 0 else -1
        )

        unhandled_main = sum(val in MERGE_UNHANDLED_NAMES for val in merge_main)
        unhandled_main_percentage = (
            100 * unhandled_main / len(main) if len(main) != 0 else 0
        )
        unhandled_feature = sum(val in MERGE_UNHANDLED_NAMES for val in merge_feature)
        unhandled_feature_percentage = (
            100 * unhandled_feature / len(feature) if len(feature) > 0 else -1
        )

        table2 += f"            {merge_tool_latex_name(merge_tool):32}"
        table2 += f" & {correct_main:5} & {round(correct_main_percentage):3}\\%"
        table2 += f" & {correct_feature:5} & {round(correct_feature_percentage):3}\\%"
        table2 += f" & {unhandled_main:5} & {round(unhandled_main_percentage):3}\\%"
        table2 += (
            f" & {unhandled_feature:5} & {round(unhandled_feature_percentage):3}\\%"
        )
        table2 += f" & {incorrect_main:5} & {round(incorrect_main_percentage):3}\\%"
        table2 += (
            f" & {incorrect_feature:5}"
            + f" & {round(incorrect_feature_percentage):3}\\% \\\\\n"
        )

    table2 += "\\end{tabular}\n"
    return table2


def main():
    """Main function"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_name", type=str, default="combined")
    parser.add_argument(
        "--full_repos_csv",
        type=Path,
        default=Path("input_data/repos_combined_with_hashes.csv"),
    )
    parser.add_argument(
        "--repos_head_passes_csv",
        type=Path,
        default=Path("results/combined/repos_head_passes.csv"),
    )
    parser.add_argument(
        "--tested_merges_path",
        type=Path,
        default=Path("results/combined/merges_tested"),
    )
    parser.add_argument(
        "--merges_path", type=Path, default=Path("results/combined/merges")
    )
    parser.add_argument(
        "--analyzed_merges_path",
        type=Path,
        default=Path("results/combined/merges_analyzed"),
    )
    parser.add_argument("--n_merges", type=int, default=100)
    parser.add_argument("--output_dir", type=Path, default=Path("results/combined"))
    parser.add_argument("--timed_merges_path", type=Path, default=None)
    args = parser.parse_args()
    output_dir = args.output_dir

    # Combine results file
    result_df_list = []
    repos = pd.read_csv(args.repos_head_passes_csv, index_col="idx")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Processing repos...", total=len(repos))
        for _, repository_data in repos.iterrows():
            progress.update(task, advance=1)
            repo_slug = repository_data["repository"]
            merge_list_file = args.tested_merges_path / (repo_slug + ".csv")
            if not merge_list_file.exists():
                raise Exception(
                    "latex_ouput.py:",
                    repo_slug,
                    "does not have a list of merges. Missing file: ",
                    merge_list_file,
                )

            try:
                merges = pd.read_csv(merge_list_file, header=0, index_col="idx")
                if len(merges) == 0:
                    raise pd.errors.EmptyDataError
            except pd.errors.EmptyDataError:
                logger.info(
                    "latex_output: Skipping "
                    + repo_slug
                    + " because it does not contain any merges."
                )
                continue
            merges = merges[merges["parents pass"]]
            if len(merges) > args.n_merges:
                merges = merges.sample(args.n_merges, random_state=42)
                merges.sort_index(inplace=True)
            merges["repository"] = repo_slug
            merges["repo-idx"] = repository_data.name
            merges["merge-idx"] = merges.index
            result_df_list.append(merges)

    result_df = pd.concat(result_df_list, ignore_index=True)
    result_df.sort_values(by=["repo-idx", "merge-idx"], inplace=True)
    result_df = result_df[
        ["repo-idx", "merge-idx"]
        + [col for col in result_df.columns if col not in ("repo-idx", "merge-idx")]
    ]
    result_df.index = (
        result_df["repo-idx"].astype(str) + "-" + result_df["merge-idx"].astype(str)
    )

    # Remove undesired states
    for merge_tool in MERGE_TOOL:
        result_df = result_df[~result_df[merge_tool.name].isin(UNDESIRABLE_STATES)]

    def merge_two_states(
        merge_result1: TEST_STATE, merge_result2: TEST_STATE
    ) -> TEST_STATE:
        """Merge two states"""
        if TEST_STATE.Tests_passed.name in (merge_result1, merge_result2):
            return TEST_STATE.Tests_passed.name
        if MERGE_STATE.Merge_failed.name in (merge_result1, merge_result2):
            return MERGE_STATE.Merge_failed.name
        if TEST_STATE.Tests_failed.name in (merge_result1, merge_result2):
            return TEST_STATE.Tests_failed.name
        if (
            merge_result1 == TEST_STATE.Tests_timedout.name
            and merge_result2 == TEST_STATE.Tests_timedout.name
        ):
            return TEST_STATE.Tests_timedout.name
        raise Exception("Invalid case")

    result_df["Oracle tool"] = TEST_STATE.Tests_failed.name
    for merge_tool in MERGE_TOOL:
        result_df["Oracle tool"] = result_df.apply(
            lambda row, merge_tool=merge_tool: merge_two_states(
                row["Oracle tool"], row[merge_tool.name]
            ),
            axis=1,
        )

    result_df.to_csv(args.output_dir / "result.csv", index_label="idx")

    main = result_df[result_df["branch_name"].isin(main_branch_names)]
    feature = result_df[~result_df["branch_name"].isin(main_branch_names)]

    for plot_category, merge_tools in PLOTS.items():
        plots_output_path = output_dir / "plots" / plot_category
        tables_output_path = output_dir / "tables" / plot_category
        Path(plots_output_path).mkdir(parents=True, exist_ok=True)
        Path(tables_output_path).mkdir(parents=True, exist_ok=True)

        check_fingerprint_consistency(result_df, merge_tools)

        # Figure Heat map diffing
        result = pd.DataFrame(
            {
                merge_tool: {merge_tool: 0 for merge_tool in merge_tools}
                for merge_tool in merge_tools
            }
        )
        for merge_tool1 in merge_tools:
            for merge_tool2 in merge_tools:
                # Mask for different fingerprints
                mask_diff_fingerprint = (
                    result_df[merge_tool1 + "_merge_fingerprint"]
                    != result_df[merge_tool2 + "_merge_fingerprint"]
                )

                # Mask if one of the results is in correct or incorrect names
                merge_name_flags1 = result_df[merge_tool1].isin(
                    MERGE_CORRECT_NAMES + MERGE_INCORRECT_NAMES
                )
                merge_name_flags2 = result_df[merge_tool2].isin(
                    MERGE_CORRECT_NAMES + MERGE_INCORRECT_NAMES
                )
                mask_merge_name = merge_name_flags1 | merge_name_flags2

                # Calculate the result
                result.loc[merge_tool1, merge_tool2] = (
                    mask_diff_fingerprint & mask_merge_name
                ).sum()

        # Transform the result into a numpy array
        _, ax = plt.subplots(figsize=(8, 6))
        result_array = np.tril(result.to_numpy())
        latex_merge_tool = [
            "\\mbox{" + merge_tool_latex_name(i) + "}" for i in result.columns
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            heatmap = sns.heatmap(
                result_array,
                annot=True,
                ax=ax,
                xticklabels=latex_merge_tool,  # type: ignore
                yticklabels=latex_merge_tool,  # type: ignore
                mask=np.triu(np.ones_like(result, dtype=bool), k=1),
                cmap="Blues",
                annot_kws={"size": 6},
            )
        heatmap.set_yticklabels(labels=heatmap.get_yticklabels(), va="center")
        heatmap.set_xticklabels(
            labels=heatmap.get_xticklabels(),
            rotation=45,
            ha="right",
            rotation_mode="anchor",
        )
        plt.tight_layout()
        plt.savefig(plots_output_path / "heatmap.pgf")
        plt.savefig(plots_output_path / "heatmap.pdf")
        plt.close()
        # Correct the path to the stored image in the pgf file.
        with open(plots_output_path / "heatmap.pgf", "rt", encoding="utf-8") as f:
            file_content = f.read()
        file_content = file_content.replace(
            "heatmap-img0.png", f"{plots_output_path}/heatmap-img0.png"
        )
        with open(plots_output_path / "heatmap.pgf", "wt", encoding="utf-8") as f:
            f.write(file_content)

        incorrect = []
        correct = []
        unhandled = []
        for merge_tool in merge_tools + ["Oracle tool"]:
            merge_tool_status = result_df[merge_tool]
            correct.append(sum(val in MERGE_CORRECT_NAMES for val in merge_tool_status))
            incorrect.append(
                sum(val in MERGE_INCORRECT_NAMES for val in merge_tool_status)
            )
            unhandled.append(
                sum(val in MERGE_UNHANDLED_NAMES for val in merge_tool_status)
            )
            assert incorrect[-1] + correct[-1] + unhandled[-1] == len(merge_tool_status)
            assert (
                incorrect[0] + correct[0] + unhandled[0]
                == incorrect[-1] + correct[-1] + unhandled[-1]
            )

        # Cost plot
        max_cost_intersection = 0
        for idx, merge_tool in enumerate(merge_tools):
            if incorrect[idx] == 0:
                continue
            max_cost_intersection = max(
                max_cost_intersection,
                ((unhandled[idx] + incorrect[idx] + correct[idx]) - unhandled[idx])
                * 1.0
                / incorrect[idx],
            )

        _, ax = plt.subplots()
        for idx, merge_tool in enumerate(merge_tools):
            results = []
            for cost_factor in np.linspace(1, max_cost_intersection, 1000):
                score = unhandled[idx] * 1 + incorrect[idx] * cost_factor
                score = score / (unhandled[idx] + incorrect[idx] + correct[idx])
                score = 1 - score
                results.append(score)
            line_style = [(idx, (1, 1)), "--", "-."][idx % 3]
            ax.plot(
                np.linspace(1, max_cost_intersection, 1000),
                results,
                label=merge_tool_latex_name(merge_tool),
                linestyle=line_style,
                linewidth=3,
                alpha=0.8,
            )
        plt.xlabel("Incorrect merges cost factor $k$")
        plt.ylabel("\\mbox{Effort Reduction}")
        plt.xlim(0, max_cost_intersection)
        plt.ylim(-0.02, 0.6)
        plt.legend()
        plt.tight_layout()
        plt.savefig(plots_output_path / "cost_without_manual.pgf")
        plt.savefig(plots_output_path / "cost_without_manual.pdf")

        # Cost plot with manual merges
        ax.plot(
            np.linspace(1, max_cost_intersection, 1000),
            np.zeros(1000),
            label="Manual Merging",
            color="red",
        )
        plt.xlim(0, max_cost_intersection)
        plt.ylim(-0.02, 0.6)
        plt.legend()
        plt.tight_layout()
        plt.savefig(plots_output_path / "cost_with_manual.pgf")
        plt.savefig(plots_output_path / "cost_with_manual.pdf")

        # Cost plot with Oracle merges
        results = []
        for cost_factor in np.linspace(1, max_cost_intersection, 1000):
            score = unhandled[-1] * 1 + incorrect[-1] * cost_factor
            score = score / (unhandled[-1] + incorrect[-1] + correct[-1])
            score = 1 - score
            results.append(score)

        ax.plot(
            np.linspace(1, max_cost_intersection, 1000),
            results,
            label="Oracle",
            linestyle="-",
            linewidth=3,
            alpha=0.8,
        )
        plt.xlim(0, max_cost_intersection)
        plt.ylim(-0.02, 0.6)
        plt.legend()
        plt.tight_layout()
        plt.savefig(plots_output_path / "cost_with_oracle.pgf")
        plt.savefig(plots_output_path / "cost_with_oracle.pdf")
        plt.close()

        # Table results
        with open(
            tables_output_path / "table_summary.tex", "w", encoding="utf-8"
        ) as file:
            file.write(
                build_table1(result_df, merge_tools, correct, unhandled, incorrect)
            )

        # Table results with Oracle
        with open(
            tables_output_path / "table_summary_with_oracle.tex", "w", encoding="utf-8"
        ) as file:
            file.write(
                build_table1(
                    result_df,
                    merge_tools + ["Oracle tool"],
                    correct,
                    unhandled,
                    incorrect,
                )
            )

        # Printed Table
        my_table = PrettyTable()
        my_table.field_names = [
            "Merge Tool",
            "Correct Merges",
            "Incorrect Merges",
            "Unhandled Merges",
        ]
        for merge_tool_idx, merge_tool in enumerate(merge_tools + ["Oracle tool"]):
            my_table.add_row(
                [
                    merge_tool_latex_name(merge_tool),
                    correct[merge_tool_idx],
                    incorrect[merge_tool_idx],
                    unhandled[merge_tool_idx],
                ]
            )

        logger.success(my_table)

        # Table by merge source
        with open(
            tables_output_path / "table_feature_main_summary.tex",
            "w",
            encoding="utf-8",
        ) as file:
            file.write(build_table2(main, merge_tools, feature))

        with open(
            tables_output_path / "table_main_feature_summary_oracle.tex",
            "w",
            encoding="utf-8",
        ) as file:
            file.write(build_table2(feature, merge_tools + ["Oracle tool"], main))

        # Table run time
        if args.timed_merges_path:
            table3 = """% Do not edit.  This file is automatically generated.
\\begin{tabular}{c|c|c|c}
    & \\multicolumn{3}{c}{Run time (seconds)} \\\\
    Tool & Mean & Median & Max \\\\
    \\hline\n"""
            timed_df = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task("Processing timed merges...", total=len(repos))
                for _, repository_data in repos.iterrows():
                    progress.update(task, advance=1)
                    repo_slug = repository_data["repository"]
                    merges = pd.read_csv(
                        Path(args.timed_merges_path) / f"{repo_slug}.csv",
                        header=0,
                    )
                    timed_df.append(merges)
                timed_df = pd.concat(timed_df, ignore_index=True)

            for merge_tool in merge_tools:
                table3 += f"    {merge_tool_latex_name(merge_tool):32}"
                for f in [np.mean, np.median, np.max]:
                    run_time = f(timed_df[merge_tool + "_run_time"])
                    if run_time < 10:
                        table3 += f" & {run_time:0.2f}"
                    elif run_time < 100:
                        table3 += f" & {run_time:0.1f}"
                    else:
                        table3 += f" & {round(run_time)}"
                table3 += " \\\\\n"
            table3 += "\\end{tabular}\n"

            with open(
                tables_output_path / "table_run_time.tex",
                "w",
                encoding="utf-8",
            ) as file:
                file.write(table3)

    # Create defs.tex
    full_repos_df = pd.read_csv(args.full_repos_csv)
    repos_head_passes_df = pd.read_csv(args.repos_head_passes_csv)

    # Change from _a to A capitalizaion
    run_name_camel_case = args.run_name.split("_")[0] + "".join(
        x.title() for x in args.run_name.split("_")[1:]
    )

    output = "% Dataset and sample numbers\n"
    output = latex_def(run_name_camel_case + "ReposInitial", len(full_repos_df))
    output += latex_def(run_name_camel_case + "ReposValid", len(repos_head_passes_df))

    # Assuming args.merges_path and other variables are defined elsewhere in your code
    count_merges_initial = 0
    count_non_trivial_merges = 0
    count_non_trivial_repos = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(
            "Processing merges...", total=len(repos_head_passes_df)
        )
        for _, repository_data in repos_head_passes_df.iterrows():
            progress.update(task, advance=1)
            merge_list_file = args.merges_path / (
                repository_data["repository"] + ".csv"
            )
            if not os.path.isfile(merge_list_file):
                continue
            try:
                df = pd.read_csv(merge_list_file, index_col=0)
            except pd.errors.EmptyDataError:
                continue
            # Ensure notes column is treated as string
            df["notes"] = df["notes"].astype(str)
            count_merges_initial += len(df)
            # Use na=False to handle NaN values properly
            non_trivial_mask = df["notes"].str.contains(
                "a parent is the base", na=False
            )
            count_non_trivial_merges += non_trivial_mask.sum()
            count_non_trivial_repos += non_trivial_mask.any()

    # Assuming output and latex_def functions are defined elsewhere in your code
    output += latex_def(run_name_camel_case + "MergesInitial", count_merges_initial)
    output += latex_def(run_name_camel_case + "MergesPer", args.n_merges)
    output += latex_def(
        run_name_camel_case + "MergesNonTrivial", count_non_trivial_merges
    )
    output += latex_def(
        run_name_camel_case + "ReposNonTrivial", count_non_trivial_repos
    )

    count_merges_java_diff = 0
    count_repos_merges_java_diff = 0
    count_merges_diff_and_parents_pass = 0
    count_repos_merges_diff_and_parents_pass = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(
            "Processing merges...", total=len(repos_head_passes_df)
        )
        for _, repository_data in repos_head_passes_df.iterrows():
            progress.update(task, advance=1)
            merge_list_file = args.analyzed_merges_path / (
                repository_data["repository"] + ".csv"
            )
            if not os.path.isfile(merge_list_file):
                continue
            try:
                df = pd.read_csv(merge_list_file, index_col=0)
            except pd.errors.EmptyDataError:
                continue
            if len(df) == 0:
                continue
            count_merges_java_diff += df["diff contains java file"].dropna().sum()
            count_merges_diff_and_parents_pass += df["test merge"].dropna().sum()
            if df["diff contains java file"].dropna().sum() > 0:
                count_repos_merges_java_diff += 1
            if df["test merge"].dropna().sum() > 0:
                count_repos_merges_diff_and_parents_pass += 1

    output += latex_def(run_name_camel_case + "MergesJavaDiff", count_merges_java_diff)
    output += latex_def(
        run_name_camel_case + "ReposJavaDiff", count_repos_merges_java_diff
    )
    output += latex_def(
        run_name_camel_case + "MergesJavaDiffAndParentsPass",
        count_merges_diff_and_parents_pass,
    )
    output += latex_def(
        run_name_camel_case + "ReposJavaDiffAndParentsPass",
        count_repos_merges_diff_and_parents_pass,
    )

    repos = 0
    count = 0
    full = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(
            "Processing merges...", total=len(repos_head_passes_df)
        )
        for _, repository_data in repos_head_passes_df.iterrows():
            progress.update(task, advance=1)
            merge_list_file = args.tested_merges_path / (
                repository_data["repository"] + ".csv"
            )
            if not os.path.isfile(merge_list_file):
                continue
            try:
                merges = pd.read_csv(merge_list_file, index_col=0)
            except pd.errors.EmptyDataError:
                continue
            if len(merges) > 0:
                repos += 1
            # Makre sure each element has "parents pass" set to True
            for _, merge in merges.iterrows():
                assert merge["parents pass"]
                assert merge["test merge"]
                assert merge["diff contains java file"]
            count += len(merges)
            if len(merges) == args.n_merges:
                full += 1

    output += latex_def(run_name_camel_case + "ReposSampled", repos)
    output += latex_def(run_name_camel_case + "MergesSampled", count)
    output += latex_def(run_name_camel_case + "ReposYieldedFull", full)
    output += latex_def(
        run_name_camel_case + "ReposTotal", len(result_df["repository"].unique())
    )
    output += latex_def(run_name_camel_case + "MergesTotal", len(result_df))

    output += "\n% Results\n"

    spork_correct = len(result_df[result_df["spork"].isin(MERGE_CORRECT_NAMES)])
    ort_correct = len(result_df[result_df["gitmerge_ort"].isin(MERGE_CORRECT_NAMES)])
    output += latex_def(
        run_name_camel_case + "SporkOverOrtCorrect", spork_correct - ort_correct
    )

    spork_incorrect = len(result_df[result_df["spork"].isin(MERGE_INCORRECT_NAMES)])
    ort_incorrect = len(
        result_df[result_df["gitmerge_ort"].isin(MERGE_INCORRECT_NAMES)]
    )
    output += latex_def(
        run_name_camel_case + "SporkOverOrtIncorrect", spork_incorrect - ort_incorrect
    )

    output += latex_def(run_name_camel_case + "MainBranchMerges", len(main))
    output += latex_def(
        run_name_camel_case + "MainBranchMergesPercent",
        round(len(main) * 100 / len(result_df)),
    )
    output += latex_def(run_name_camel_case + "OtherBranchMerges", len(feature))
    output += latex_def(
        run_name_camel_case + "OtherBranchMergesPercent",
        round(len(feature) * 100 / len(result_df)),
    )
    output += latex_def(
        run_name_camel_case + "ReposJava",
        len(full_repos_df),
    )

    output += "\n% Timeout\n"
    output += latex_def(
        run_name_camel_case + "ParentTestTimeout", str(TIMEOUT_TESTING_PARENT // 60)
    )
    output += latex_def(
        run_name_camel_case + "MergeTestTimeout", str(TIMEOUT_TESTING_MERGE // 60)
    )

    with open(args.output_dir / "defs.tex", "w", encoding="utf-8") as file:
        file.write(output)


if __name__ == "__main__":
    main()
