import pandas as pd

df = pd.read_csv("data/result.csv")


for i in ["git merge","spork","intellimerge"]:
    for j in [-2,-1,1,2,3,5,6]:
        instances = sum(df[i] == j)
        print(i,j,instances)