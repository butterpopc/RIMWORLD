import ctypes
def ssh(s):
    n=23
    for ch in s:
        n=ctypes.c_int32(n*31+ord(ch)).value
    return n
def cmod(a,b):
    r=abs(a)%b
    return -r if a<0 else r
def sh(s,k=0):
    return (cmod(ssh(s)+k,65535)) & 0xFFFF
names="""Soil SoilRich Gravel Sand MarshyTerrain Mud Marsh WaterShallow WaterDeep WaterMovingShallow WaterMovingChestDeep WaterOceanShallow WaterOceanDeep Riverbank Granite_Rough Granite_RoughHewn Granite_Smooth Sandstone_Rough Sandstone_RoughHewn Sandstone_Smooth Limestone_Rough Limestone_RoughHewn Limestone_Smooth Slate_Rough Slate_RoughHewn Slate_Smooth Marble_Rough Marble_RoughHewn Marble_Smooth Ice PackedDirt Concrete PavedTile WoodPlankFloor BrokenAsphalt LichenCovered MossyTerrain SoftSand Chalk Clay Basalt_Rough Peat Moss MossPatch Bridge HeavyBridge
RoofConstructed RoofRockThin RoofRockThick
Granite Sandstone Limestone Slate Marble ChunkGranite ChunkSandstone ChunkLimestone ChunkSlate ChunkMarble MineableSteel MineableSilver MineableGold MineablePlasteel MineableUranium MineableJade MineableComponentsIndustrial MineableObsidian CollapsedRocks Plant_Grass Steel ChunkSlagSteel Vacstone ChunkVacstone""".split()
targets={34465,10040,56931,27449,65097,32883,42032,41863,11445,38103,63102,6764,49581,14838,59853,50215,10820,6699,5133,64138,323,64468,27293,11383,45390,13103,43357,21442,63717,7015,8319,23537}
for n in names:
    for k in range(3):
        h=sh(n,k)
        if h in targets: print(n,k,h)
