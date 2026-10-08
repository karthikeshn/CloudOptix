import sys
import os
import boto3

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils import cur_processor as cur_integration

list1 = [
    "snap-037470754eeed9609",
    "snap-076f2cb8e96167ba7",
    "snap-0c091eab6189ac884",
    "snap-0e4424ecd02832b79",
    "snap-0fe961e2d7dd99fcc"
]

list2_raw = """snap-0003bf862a6285c6e
snap-0008ce5c92da31822
snap-000aa1956be7b5da8
snap-001e7a1c6ac044645
snap-00207a9110324943e
snap-0029a430db9690edc
snap-002e51418f854ff2f
snap-003168491f3e12dc9
snap-0037ef850782a3f72
snap-004c6198c2fa0b580
snap-0064384d268c87001
snap-00875dc5b8d16b3f8
snap-0089b70d0d0bcc7bb
snap-008aad65c67a36d96
snap-00a0c65567e2fbb21
snap-00a3a08521ca6cd94
snap-00aeeb2b8ce5d2054
snap-00b78b7b95405a2fc
snap-00bc49b886ef3565d
snap-00c6d14a85e840e39
snap-00c9052985d801aed
snap-00d19fe3063d329bf
snap-00d6646d6057464d0
snap-00f299e7ccaa6bd6c
snap-00f5bbbefe529e563
snap-00fe46671426631c8
snap-010576370d931ddbb
snap-012960f01775d2bf3
snap-0135351b7bf2badd8
snap-0139bbf25b0a8d85b
snap-0141487e1b5d0c18a
snap-0151b8fd206bc38b1
snap-0157fdb93682bc0fe
snap-01702ddda0e17ed7d
snap-0177568081e37e509
snap-0178a026f69e436e5
snap-017bc6373a5ac50ba
snap-01839f6ec96243a1e
snap-019a1a9956a22aaa6
snap-01b77b75f4aa72260
snap-01bd0ce2481ab1384
snap-01bdc50301f42457f
snap-01d2682a5b3b162e5
snap-01d86bc304d37544c
snap-01df19b98e26c9d04
snap-01e385de3649b1b10
snap-01e85b2a19835f766
snap-01fda5995e83b44a3
snap-01fefe2a9606478fd
snap-020eb2d4cbb241171
snap-021a4b8bd7678f4fa
snap-02295970f41e727f6
snap-022dcbcc4b1c11079
snap-023936d2902500349
snap-023b7c1fde6c317dd
snap-0240ffa09cca48479
snap-0243d78d0edab9519
snap-0243e6589d118a3db
snap-0245ad07c47634d71
snap-02647e501c439d4b2
snap-026ce68e740cedf99
snap-026d4b9e5f7b81140
snap-0277528819bbe5785
snap-0284dd114cf0d2197
snap-029d5a37e128524cf
snap-02a1a9c565e0b5102
snap-02b488dcd4c239b63
snap-02b48b0a42bf60a2a
snap-02b9effc61145ab1a
snap-02c5bef2b15c03457
snap-02d7728828602de3f
snap-02d958f46bb8fe677
snap-02dcd3b2df3afbc4d
snap-02e623cad7fdaeebd
snap-02e6395834002d2a4
snap-02fa937e40f06d964
snap-02fd2fa3a00fcfbb1
snap-03112df985331520c
snap-032a3d927f8f3371e
snap-03388c0d98a8e39dd
snap-035ae65a2c8df50fe
snap-0363ece7e5b6a985a
snap-038a8f3f7a5240b4a
snap-038b7be67e6d8bd1e
snap-039198fd6992fbbf3
snap-03aa48dac082c5ef4
snap-03af30649537a859c
snap-03b7a58dee8c86456
snap-03b7aa9dc26f7d430
snap-03b98ff9061513acf
snap-03be45feaff428d13
snap-03e03eeab60869488
snap-03e8bc104d4daf634
snap-03f0dbb647fdeaacd
snap-03fe96df476957059
snap-03ff08ce9fb1412be
snap-0409ffbe3ac944668
snap-0430dad12686daf4b
snap-044156a22927b62b0
snap-04646ab7368d2342c
snap-04805da594f882d3c
snap-0482f7896d4f3f532
snap-0484ae322fe2ebcd0
snap-0486f51979d630afa
snap-04a012e3227e87a7b
snap-04ae474f0d436b341
snap-04bf06243b303035c
snap-04c51dc0092c1995e
snap-04d48d0781a5db5c4
snap-04fae24a608c29443
snap-04fc7638b000f3f1f
snap-0500315b7b06d0649
snap-0508a8cbc09697771
snap-050b466c36c39a76a
snap-0518efc1266a97cee
snap-0519d69251fe74702
snap-051ac24ec92b8863b
snap-05213018a3564798b
snap-0521c9b86d318fb4a
snap-053eda4d4ba083e25
snap-053f5ca04fee383bd
snap-05848fd590c908ef3
snap-05a1bc47384595be1
snap-05af3b4aeca24c912
snap-05cf6cb9cb511089b
snap-05cf93342fac4c1c2
snap-05d07a3983b3f1752
snap-05d5c37461b0c3e2c
snap-05e5b72fe931dce89
snap-05fb014589012e932
snap-061f32bef4d9575f6
snap-0662e8ee5158799ac
snap-06665457a8596552c
snap-066b73987e74ab969
snap-066ce0f0bc8ad7a9b
snap-067c4a7e8e8f94709
snap-06828810a8bdbdd12
snap-068fb8ec0fe124cae
snap-0698a7c71daab6b88
snap-069c2a20f570cefb8
snap-069cdaa4846d661c4
snap-06a4958ca6cc28bca
snap-06b23c04fe8676126
snap-06b583219e89ad4f0
snap-06be87deb8ec6a162
snap-06f0b78f04edd6788
snap-06f68b87756cf3b7c
snap-06fae9a0484047c08
snap-07085195f48619e45
snap-07198ce303777fa58
snap-07447ec0e464da1e4
snap-075ae5f66cd05454c
snap-0778702f55eb3610f
snap-077f16f1c735c5fae
snap-0785671cd5d5f3eb7
snap-0793d4d8b1cd3c176
snap-079e637bc9ba854b3
snap-07a8b3318af75cce3
snap-07b28e76115ed137b
snap-07b4f5d9ff575d1f1
snap-07bb52d591fd02990
snap-07c9c082b0f7a342c
snap-07cabab63fbe3b63d
snap-07d1f7192be5b0c6a
snap-07d9016966ee1ef58
snap-07da6dceb0fdc09b9
snap-07ddb12e2bbfed8b3
snap-07f4c3b4d71dac499
snap-07ff29b762b9278a8
snap-080b3de8913a59045
snap-0815c59469dec6bce
snap-081db3c0e45b27a6e
snap-0827c804ca6b4ac85
snap-08378ac0dc79f5db6
snap-083ba34cf51b15a9f
snap-085847622f675058e
snap-085bf93d7ec691ef6
snap-085d46584ba783981
snap-08a34901faa9e3b9b
snap-08b1e1a7ad919caf1
snap-08b5875a5c6f73d56
snap-08d19e8a7d3a20a66
snap-08d62528433187fb0
snap-08f0c67b3b58839c1
snap-08feaefb3e4e7c755
snap-090d6d8a0fc381d9a
snap-091b211525c6f21e9
snap-092418a4f3e43cfd1
snap-0941cd3f8350d7fff
snap-095bf30e7664bf97c
snap-095c16061a7473e71
snap-095cabc5f1c903684
snap-095eada8f3e844e7b
snap-09682d5b0ead2cac7
snap-09760c20142e7958b
snap-09887fd0e0f51485d
snap-09a66a2c9b2666ad9
snap-09b146a64e7237c6a
snap-09b73261dfdbbd049
snap-09d62a6a086709670
snap-09f2efa3ee9d192cb
snap-09f9e0e2a49c9db68
snap-0a06c22b8b3bb65c9
snap-0a1e4055ed22fb247
snap-0a29e3124edae656d
snap-0a442dbcc8d3a82e3
snap-0a5114daae0ee5a85
snap-0a689816d793e9783
snap-0a6f3afdc2a28e747
snap-0a70123ec98ecad81
snap-0a7060571a485350a
snap-0a765bbc080a76d14
snap-0a7803929c1a8dcc3
snap-0a7eefaad4b9a4df7
snap-0a93a40a6cb75f245
snap-0a9ad5197d6ddf6cf
snap-0ac6e47fa8ff30f83
snap-0ace3d24a4c16a6f8
snap-0af5a76b12d1d92fb
snap-0afa5b11ab3bc7189
snap-0afe107d2b8cdec7e
snap-0b0263c6555a018a6
snap-0b1f75152538a3c9d
snap-0b331d2cc980eadc8
snap-0b338bcccd9cb2ced
snap-0b37929ef1648c640
snap-0b3c2e5822916a414
snap-0b46ad2acff5e1a54
snap-0b56f27ec9518004e
snap-0b628cc023a31f509
snap-0b954f0b31452bd9d
snap-0ba1bd1cf4487d27a
snap-0ba668a7df33299d8
snap-0bacba64df1355d76
snap-0bad9f55cc8460f42
snap-0baea9f62cd3ed913
snap-0bb2ffe8569bab613
snap-0bb751ccc4ee25bbb
snap-0bb8af5e9d1a35e0c
snap-0bbf77aedc1de3a27
snap-0bc6cd93eecdd44d0
snap-0bd266218779c7b51
snap-0be005d276df59604
snap-0be9565259ba13f3c
snap-0bebec214cd242f8c
snap-0c00bfc98e68345c0
snap-0c0aa992969d6d457
snap-0c1355dc236bdf118
snap-0c335efc6b7326828
snap-0c3e3ffe81f4ab373
snap-0c43662f533b377b2
snap-0c4852d4613485fc7
snap-0c4d3a1031bb73320
snap-0c50ba0bc6e18ec59
snap-0c55fe7c0a55ae976
snap-0c5d15ab83dedcf96
snap-0c63433fd84a776b4
snap-0c7248c30707858aa
snap-0c78778550f6f5bc9
snap-0c7c43db316a0f76a
snap-0cb084100fba83cc8
snap-0cc2721d8cdde8aa4
snap-0cd1177bda8d7b453
snap-0cd1ab5346c03c17d
snap-0cda8e8c95e978b88
snap-0ce3502f301f2508c
snap-0ce7802a4f992f5aa
snap-0ceaf4019975d2c45
snap-0cf31ad43a68c7a8a
snap-0cf9bf31cfb006202
snap-0cfec0922ed889889
snap-0d10b9f5cedb0d928
snap-0d1abc7da423e920c
snap-0d1af5f83473c0b23
snap-0d1d3d2c39a2b113b
snap-0d2515f9c42f6c31b
snap-0d2ddca166859722a
snap-0d37e371b0b1f8abc
snap-0d3cd9ec48693e579
snap-0d4816e670f307714
snap-0d50fe5b12fa31085
snap-0d592065b9faa1ccf
snap-0d6be2bae096b483f
snap-0d9d563a65c2b8f45
snap-0da097fc9e3e66d06
snap-0dac1099fd3b519af
snap-0db502c0414823c9c
snap-0dde97651cec05c3b
snap-0de4579d73805318c
snap-0de641552079c7806
snap-0deb79756f14e7895
snap-0dff3f1afff10a546
snap-0e02cb808eca8bca9
snap-0e0e147d55f342210
snap-0e19386a2bd9487e9
snap-0e509a01694d68807
snap-0e5499ee85dcc0548
snap-0e6f8c16e1d9aef25
snap-0e77a07ac3bd0441d
snap-0e870ef78771a373d
snap-0e92d4d6ba19753e9
snap-0e95b4270f4484011
snap-0ea0693efebd54d4b
snap-0eb2f36c4e73cec1f
snap-0eb42f16fc6060c1a
snap-0eb4c061230c23dc8
snap-0eb66657b59cdf998
snap-0efb5084726db522b
snap-0f00efab379766a3b
snap-0f082fc129be13288
snap-0f1038ec39e898763
snap-0f1691a21e63306f6
snap-0f3125cc8eeab5b19
snap-0f336cffa26c26514
snap-0f3407ea9a3fed47f
snap-0f3ce0b54ca2076d4
snap-0f4038e65e7ce1e0e
snap-0f4b3a0487ef3c91f
snap-0f4ce15c3e90ed191
snap-0f5748679220cb609
snap-0f5f503029a6d4ab3
snap-0f6e808fff3bc2dd0
snap-0f73b61b34b14c5f5
snap-0f7d1d6b75649b210
snap-0f8888936db5264b6
snap-0f9a164fb558f11a1
snap-0fbf6e10c36547552
snap-0fc395441fc73607f
snap-0fd0ad63697ba2b6b
snap-0ff784225c03c2c44"""

list2 = [x.strip() for x in list2_raw.split('\n') if x.strip()]

def main():
    sts = boto3.client('sts', region_name='us-east-1')
    account_id = sts.get_caller_identity()["Account"]
    
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "snapshot_costs.txt")
    
    with open(output_path, "w") as f:
        f.write("Snapshot Cost Report\n")
        f.write("====================\n\n")
        
        def write_list(snaps, name):
            f.write(f"--- {name} ---\n")
            for snap in snaps:
                cost = cur_integration.get_historical_cost(resource_id=snap, account_id=account_id, fallback_cost=None)
                if cost is not None:
                    f.write(f"{snap}: ${cost}\n")
                else:
                    f.write(f"{snap}: Not Found\n")
            f.write("\n")

        write_list(list1, "List 1 (5 snapshots)")
        write_list(list2, "List 2 (330 snapshots)")
        
    print(f"Report generated at {output_path}")

if __name__ == "__main__":
    main()
