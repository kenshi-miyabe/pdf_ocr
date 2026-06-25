# mdとpdfのペアをzip化する関数
zip-pairs() {
    local count=0
    for f in *.md; do
        # ファイルが存在しない場合のループ終了処理
        [[ -e "$f" ]] || continue

        local base="${f%.md}"
        if [[ -f "$base.pdf" ]]; then
            if zip -q "$base.zip" "$f" "$base.pdf"; then
                echo "Created: $base.zip"
                ((count++))
            else
                echo "Failed: $base.zip" >&2
            fi
        fi
    done
    echo "Done. $count pairs processed."
}
