"""Runs a merge and uses diff3 to compare it to the base and final branch of a given repo.
"""

import sys
import argparse
import subprocess
import re
import os
import shutil
import tempfile
import pandas as pd
from repo import clone_repo_to_path
from merge_tester import MERGE_STATE

# pylint: disable-msg=too-many-locals
# pylint: disable-msg=too-many-statements


def diff3_pair_analysis(
    merge_tool1: str, merge_tool2: str, results_index: int, repo_output_dir
):
    """
    Analyzes merge conflicts using the diff3 tool and opens the results in the default text viewer.

    Args:
        merge_tool (str): The merge tool to be used.
        results_index (int): The index of the repository in the results DataFrame.
        repo_output_dir (path): The path of where we want to store the results from the analysis

    Returns:
        None
    """

    # Deletes base, programmer_merge, and merge_attempt folders in repos dir
    # We do this to prevent errors if cloning the same repo into the folder twice
    shutil.rmtree("./repos", ignore_errors=True)

    # Retrieve left and right branch from hash in repo
    df = pd.read_csv("../../results/combined/result.csv")
    repo_name = df.iloc[results_index]["repository"]

    script = "../scripts/merge_tools/" + merge_tool1 + ".sh"
    repo = clone_repo_to_path(
        repo_name, "./repos/merge_attempt1"
    )  # Return a Git-Python repo object
    repo.remote().fetch()
    left_sha = df.iloc[results_index]["left"]
    repo.git.checkout(left_sha, force=True)
    print("Checking out left" + left_sha)
    repo.submodule_update()
    repo.git.checkout("-b", "TEMP_LEFT_BRANCH", force=True)
    repo.git.checkout(df.iloc[results_index]["right"], force=True)
    print("Checking out right" + df.iloc[results_index]["right"])
    repo.submodule_update()
    repo.git.checkout("-b", "TEMP_RIGHT_BRANCH", force=True)

    base_sha = subprocess.run(
        [
            "git",
            "merge-base",
            "TEMP_LEFT_BRANCH",
            "TEMP_RIGHT_BRANCH",
        ],
        cwd="./repos/merge_attempt1/" + repo_name,
        stdout=subprocess.PIPE,
        text=True,
    )
    print("Found base sha" + base_sha.stdout)

    repo2 = clone_repo_to_path(
        repo_name, "./repos/base"
    )  # Return a Git-Python repo object
    repo2.remote().fetch()
    base_sha = base_sha.stdout.strip()
    repo2.git.checkout(base_sha, force=True)
    repo2.submodule_update()

    result = subprocess.run(
        [
            script,
            repo.git.rev_parse("--show-toplevel"),
            "TEMP_LEFT_BRANCH",
            "TEMP_RIGHT_BRANCH",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )

    conflict_file_matches = re.findall(
        r"CONFLICT \(.+\): Merge conflict in (.+)", result.stdout
    )
    print(result.stdout)

    if conflict_file_matches == []:
        print("No conflict files to search")
        return

    repo3 = clone_repo_to_path(
        repo_name, "./repos/programmer_merge"
    )  # Return a Git-Python repo object
    repo3.git.checkout(df.iloc[results_index]["merge"], force=True)
    repo3.submodule_update()

    print(conflict_file_matches)

    script = "../scripts/merge_tools/" + merge_tool2 + ".sh"
    repo4 = clone_repo_to_path(
        repo_name, "./repos/merge_attempt2"
    )  # Return a Git-Python repo object
    repo4.remote().fetch()
    left_sha = df.iloc[results_index]["left"]
    repo4.git.checkout(left_sha, force=True)
    print("Checking out left" + left_sha)
    repo4.submodule_update()
    repo4.git.checkout("-b", "TEMP_LEFT_BRANCH", force=True)
    repo4.git.checkout(df.iloc[results_index]["right"], force=True)
    print("Checking out right" + df.iloc[results_index]["right"])
    repo4.submodule_update()
    repo4.git.checkout("-b", "TEMP_RIGHT_BRANCH", force=True)

    for conflict_file_match in conflict_file_matches:
        conflicting_file = str(conflict_file_match)
        conflict_path = os.path.join(repo_name, conflicting_file)
        conflict_path_merge_attempt = os.path.join(
            "./repos/merge_attempt1", conflict_path
        )

        conflict_path_base = os.path.join("./repos/base", conflict_path)
        conflict_path_programmer_merge = os.path.join(
            "./repos/programmer_merge", conflict_path
        )

        diff_results = subprocess.run(
            [
                "diff3",
                conflict_path_base,
                conflict_path_merge_attempt,
                conflict_path_programmer_merge,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Check that diff3 didn't run into missing files in the base
        error_message = "No such file or directory"
        if error_message in diff_results.stderr:
            # Since the conflict file was added in both parents we can't diff the base.
            diff_results = subprocess.run(
                [
                    "diff",
                    conflict_path_merge_attempt,
                    conflict_path_programmer_merge,
                ],
                stdout=subprocess.PIPE,
                text=True,
            )

        # Remove ._ at the end of the file name that will mess things up
        conflicting_file_base, _ = os.path.splitext(os.path.basename(conflicting_file))

        # Generate a filename for the diff result, including the new subdirectory
        diff_filename = os.path.join(
            repo_output_dir,
            str(results_index),
            merge_tool1,
            f"diff_{conflicting_file_base}.txt",
        )

        # Extract the directory part from diff_filename
        output_dir = os.path.dirname(diff_filename)

        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Write the diff results to the file
        with open(diff_filename, "w") as diff_file:
            diff_file.write(diff_results.stdout)

        # Optionally, print or log the path of the diff file
        print(f"Diff results saved to {diff_filename}")

        """

        BREAK

        """

        conflict_path = os.path.join(repo_name, conflicting_file)
        conflict_path_merge_attempt = os.path.join(
            "./repos/merge_attempt2", conflict_path
        )

        diff_results = subprocess.run(
            [
                "diff3",
                conflict_path_base,
                conflict_path_merge_attempt,
                conflict_path_programmer_merge,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Check that diff3 didn't run into missing files in the base
        error_message = "No such file or directory"
        if error_message in diff_results.stderr:
            # Since the conflict file was added in both parents we can't diff the base.
            diff_results = subprocess.run(
                [
                    "diff",
                    conflict_path_merge_attempt,
                    conflict_path_programmer_merge,
                ],
                stdout=subprocess.PIPE,
                text=True,
            )

        # Generate a filename for the diff result, including the new subdirectory
        diff_filename = os.path.join(
            repo_output_dir,
            str(results_index),
            merge_tool2,
            f"diff_{conflicting_file_base}.txt",
        )

        # Extract the directory part from diff_filename
        output_dir = os.path.dirname(diff_filename)

        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Write the diff results to the file
        with open(diff_filename, "w") as diff_file:
            diff_file.write(diff_results.stdout)

        # Optionally, print or log the path of the diff file
        print(f"Diff results saved to {diff_filename}")
