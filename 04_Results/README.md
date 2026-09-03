# Results

В Git следует хранить только небольшие итоговые таблицы/фигуры, необходимые для воспроизводимости и публикации. Большие промежуточные optimizer outputs и raw data держать во внешнем `CEF_Dy_Data/`.

Крупные reproducibility artifacts, необходимые для воспроизведения результата, могут храниться во внешнем `CEF_Dy_Data`, если tracked checkpoint/provenance явно содержит их logical external path, byte size и SHA-256. Отсутствие большого файла непосредственно в Git в таком случае не означает отсутствие canonical provenance.
