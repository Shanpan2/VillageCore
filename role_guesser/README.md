# Roles Guesser

Among Us MOD役職向けのアキネーター・クイズ機能です。


## VillageCore
VillageCoreの各種説明や概要は [こちら](README.md)


## 概要

- `/guess` で役職アキネーターを開始します。
- `/quiz` で役職クイズを開始します。
- 役職データは `role_guesser/data/roles.csv` にあります。
- データは役職説明文ではなく、役職の特徴を `true` / `false` のタグに分解したものです。

## むらびと君からの案内

むらびと君のヘルプページには、`Roles Guesser` の案内セクションを追加しています。
webサイトは[こちら](https://worker-production-9aed.up.railway.app/help#roles-guesser)から

- むらびと君本体の案内ページから `Roles Guesser` の概要を確認できます。
- `/guess` と `/quiz` の使い道を簡単に案内します。
- Wiki本文や画像を転載していないこと、役職データは特徴タグ中心で管理していることを明記します。

READMEは詳細な運用メモ、むらびと君の案内ページは利用者向けの短い入口、という分担です。

## データの扱い

この機能は、各MODのWikiや公開説明を参考にして役職の仕様を確認し、BOT用に特徴タグへ再構成しています。

`roles.csv` には、原則として以下のみを保存します。

- 役職名
- 表示名
- MOD名
- 陣営
- BOTが質問・分類するための特徴タグ

Wiki本文、Tips、Q&A、オプション表、画像などの長文・表現・素材は、そのまま転載しない方針です。

## 著作権・引用について

このBOTの役職データは、Wiki本文の丸写しではなく、役職仕様をもとにした独自の分類データです。

## 参考にさせて頂いた各種MODのリンクはこちら

[Town Of Host](https://github.com/tukasa0001/TownOfHost)
[Town Of Host K](https://github.com/KYMario/TownOfHost-K)
[Super New Roles](https://github.com/SuperNewRoles/SuperNewRoles)
[Nebula on the Ship](https://github.com/Dolly1016/Nebula)
[ExtreameRoles](https://github.com/yukieiji/ExtremeRoles)
[The Other Roles GMIA](https://github.com/GMIA-Nexus/TheOtherRolesGMIA)
