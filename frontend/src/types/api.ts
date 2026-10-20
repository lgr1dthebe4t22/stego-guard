// Типы ответов API — зеркало JSON гейтвея (internal/handler/verify.go).
// Если гейтвей изменит поля, TypeScript подсветит все места использования.

export interface EmbedResult {
  blob: Blob;           // защищённый файл для скачивания
  sha256: string;       // SHA-256 оригинала (заголовок X-Content-SHA256)
  userId: string;
  format: 'png' | 'jpeg';
}

export interface VerifyResponse {
  status: 'AUTHENTIC' | 'TAMPERED' | 'NO_WATERMARK' | string;
  authentic: boolean;
  ber: number;                    // 0.0 – 1.0
  hash_match: boolean;
  user_id: string;                // кто защитил (пусто, если метка разрушена)
  sha256: string;                 // SHA-256 проверенного файла
  heatmap_base64?: string;        // PNG зон вмешательства (только при TAMPERED)
}

export type Mode = 'embed' | 'verify';