# By Peijin 
# 2020-9-17

# Note : make sure there is enough storage!

module load dp3 # load NDPPP 

DIR='./'  # better use absolute directory
PREFIX='L700177_'


for MSfile in `ls $DIR$PREFIX*.MS -d`
do
    NDPPP msin=$MSfile msout=${MSfile/uv/autow_uv} steps=[] msin.autoweight=True
done
