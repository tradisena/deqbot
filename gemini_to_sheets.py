import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
import sys

# 1. Konfigurasi Gemini (Library Terbaru)
client_ai = genai.Client(api_key="AIzaSyA6eIf4j2RhoFHnxJU3xXUqb9lJ5h49GN0")
MODEL_ID = "gemini-2.5-flash"

# 2. Konfigurasi Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client_sheets = gspread.authorize(creds)

# Buka sheet berdasarkan URL
sheet_url = "https://docs.google.com/spreadsheets/d/1M7Tv9G82LUw-dhJt64K9BU7f1VlnvSwPr5BYRUnr4r4/edit#gid=0"
sheet = client_sheets.open_by_url(sheet_url).sheet1

def main():
    try:
        # Membaca data
        print("Sedang membaca data dari Google Sheets...")
        all_data = sheet.get_all_values()
        
        if len(all_data) < 2:
            print("Error: Baris ke-2 di Sheet masih kosong. Isi dulu datanya!")
            return

        data_mentah = all_data[1][0] # Baris 2, Kolom A
        print(f"\nData ditemukan di A2: {data_mentah}")
        
        # --- INPUT PROMPT LANGSUNG ---
        print("\n" + "="*40)
        instruksi = input("Tulis perintah Anda untuk AI: ")
        print("="*40)

        prompt_lengkap = f"Instruksi: {instruksi}\nData: {data_mentah}"
        
        print("\nMenghubungi Gemini...")
        response = client_ai.models.generate_content(
            model=MODEL_ID,
            contents=prompt_lengkap
        )
        
        hasil_ai = response.text
        
        # Menulis kembali ke Sheet (Baris 2, Kolom B)
        sheet.update_cell(2, 2, hasil_ai)
        
        print("\nBERHASIL!")
        print(f"Hasil AI: {hasil_ai}")
        print("Data sudah dimasukkan ke Sheet kolom B baris 2.")

    except Exception as e:
        print(f"\nTerjadi Kesalahan: {e}")

if __name__ == "__main__":
    main()