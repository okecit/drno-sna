# Lensa Teori dalam DRNO (v0.3)

| Lensa | Operasionalisasi | Berkas ekspor | Batas tafsir |
|---|---|---|---|
| Structural Holes (Burt, 1992) | Constraint, effective size; peran broker Gould & Fernandez (1989) per komunitas | broker_nodes.csv | Posisi struktural, bukan peran organisasi atau pengaruh |
| Strength of Weak Ties (Granovetter, 1973) | Ikatan lemah = 1 interaksi tak berbalas; proporsi lemah pada jembatan vs dalam komunitas | tie_summary.csv | Kekuatan ikatan diukur dari interaksi publik, bukan kedekatan emosional |
| Homofili (McPherson dkk., 2001) | E-I index (Krackhardt & Stern, 1988) + uji permutasi 500x; assortativity; matriks pencampuran | homophily.csv, mixing_stance.csv | Tidak membedakan seleksi dari pengaruh (Shalizi & Thomas, 2011); atribut = label mesin |
| Social Identity Theory (Tajfel & Turner, 1979) | Pronomina in-group/out-group per 1.000 kata per komunitas (eksploratif) | identity_markers.csv | Indikator linguistik kasar; bukan ukuran identitas |

## Lensa yang tidak dipakai, dan alasannya
- **Efficiency vs Security (Baker & Faulkner, 1993)**: dirancang untuk jaringan klandestin yang batasnya diketahui. DRNO mengamati percakapan publik tentang radikalisasi; menerapkan lensa ini berarti memperlakukan akun publik seolah sel rahasia. Lebih tepat untuk studi whole-network sel yang terdokumentasi (bandingkan Koschade, 2006).
- **Scale-Free (Barabási & Albert, 1999)**: berguna sebagai uji diagnostik distribusi derajat, bukan teori penjelas; klaim bebas-skala pada jaringan nyata juga diperdebatkan (Broido & Clauset, 2019).
