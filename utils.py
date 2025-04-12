import pandas as pd
import numpy as np # Required for NaN comparison
import google.generativeai as genai
import os
from dotenv import load_dotenv
import re
from datetime import datetime
import sys
import json
import pickle

# تحميل مفتاح API من ملف .env
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# إعداد Gemini API
model = None
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        # استخدم أحدث نموذج Flash أو النموذج التجريبي المحدد
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        # Test connection (optional)
        # model.generate_content("Test")
        print("Gemini API configured successfully.")
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        model = None # Ensure model is None if configuration fails
else:
    print("Warning: GEMINI_API_KEY not found in .env file. AI analysis will be disabled.")

# --- دالة تحميل البيانات المحسنة ---
def load_data(uploaded_file):
    """Loads data from an uploaded Excel file into a Pandas DataFrame."""
    try:
        # التحقق من نوع الملف من خلال اسمه
        file_name = uploaded_file.name.lower()
        
        if file_name.endswith('.csv'):
            # إذا كان ملف CSV، استخدم وظيفة قراءة CSV
            try:
                # محاولة قراءة الملف CSV بالترميز الافتراضي
                df = pd.read_csv(uploaded_file)
                print("Successfully loaded CSV file")
            except UnicodeDecodeError:
                # إذا فشل، جرب بترميز آخر
                df = pd.read_csv(uploaded_file, encoding='latin1')
                print("Successfully loaded CSV file with latin1 encoding")
        else:
            # محاولة قراءة ملف Excel
            try:
                # تثبيت xlrd بشكل صريح إذا كان ملف .xls
                if file_name.endswith('.xls'):
                    try:
                        print("Trying to use xlrd for .xls file...")
                        # محاولة تثبيت xlrd إذا كان غير موجود
                        try:
                            import xlrd
                            print(f"xlrd version: {xlrd.__version__}")
                        except ImportError:
                            print("xlrd not found, attempting to install...")
                            import subprocess
                            subprocess.check_call([sys.executable, "-m", "pip", "install", "xlrd>=2.0.1"])
                            import xlrd
                            print(f"xlrd installed, version: {xlrd.__version__}")
                        
                        # استخدام محرك xlrd
                        df = pd.read_excel(uploaded_file, engine='xlrd')
                    except Exception as e_xlrd:
                        print(f"xlrd engine failed: {e_xlrd}")
                        # إذا فشل xlrd، حاول استخدام سلاسل نصية CSV
                        print("Trying to read .xls file as CSV (some .xls files are actually CSV files with wrong extension)...")
                        try:
                            df = pd.read_csv(uploaded_file)
                        except Exception as e_csv:
                            print(f"CSV attempt failed: {e_csv}")
                            raise Exception("Could not read .xls file with any method")
                else:
                    # لملفات .xlsx، استخدم openpyxl
                    df = pd.read_excel(uploaded_file, engine='openpyxl')
            except Exception as e_excel:
                print(f"Excel reading failed: {e_excel}")
                # كمحاولة أخيرة، جرب قراءة الملف كـ CSV حتى لو لم يكن بامتداد .csv
                try:
                    print("Trying to read as CSV as last resort...")
                    df = pd.read_csv(uploaded_file)
                    print("Successfully read file as CSV")
                except Exception as e_csv:
                    print(f"Last resort CSV reading failed: {e_csv}")
                    raise Exception(f"Failed to read file with any method. Original error: {e_excel}")

        # 1. تنظيف أسماء الأعمدة (إزالة المسافات البادئة/اللاحقة، تحويل إلى حالة الثعبان الصغيرة)
        original_columns = df.columns.tolist()
        df.columns = [col.strip().lower().replace(' ', '_').replace('.', '') for col in df.columns]
        # إنشاء قاموس لربط الأسماء الأصلية بالجديدة إذا لزم الأمر لاحقًا
        column_mapping = dict(zip(original_columns, df.columns))
        print("Original columns:", original_columns)
        print("Cleaned columns:", df.columns.tolist())
        print("Column mapping:", column_mapping)


        # 2. تحديد أعمدة التاريخ الصحيحة (بالأسماء النظيفة)
        date_cols_cleaned = ['date_reception', 'date_de_reparation', 'date_production']

        # 3. التحقق من وجود الأعمدة قبل المعالجة
        missing_cols = [col for col in date_cols_cleaned if col not in df.columns]
        if missing_cols:
            print(f"Warning: Expected date columns missing: {missing_cols}. Date analysis might be incomplete.")
            # يمكنك أن تقرر هنا إما إيقاف المعالجة أو المتابعة بدون الأعمدة المفقودة

        # تواريخ عنصر نائب للبحث عنها
        placeholder_dates_str = ["30/12/1899", "1899-12-30", "01/01/1753", "1753-01-01"]
        # تعريف تاريخ 11-11-2011 كتاريخ خاص يشير إلى المنتجات القديمة
        old_product_date_str = ["11/11/2011", "2011-11-11"]
        special_old_product_date = pd.to_datetime('2011-11-11')

        # 4. معالجة كل عمود تاريخ متوقع
        for col in date_cols_cleaned:
            if col in df.columns:
                # تحويل القيم التي تشبه التواريخ النائبة إلى None أولاً
                # قد تحتاج إلى تعديل هذا بناءً على كيفية تخزين Excel للتواريخ
                df[col] = df[col].apply(lambda x: None if isinstance(x, str) and any(p in x for p in placeholder_dates_str) else x)
                df[col] = df[col].apply(lambda x: None if isinstance(x, datetime) and (x.year == 1899 or x.year == 1753) else x)
                
                # نحافظ على تاريخ 11-11-2011 كما هو إذا كان العمود هو تاريخ الإنتاج
                if col == 'date_production':
                    # حفظ القيم التي تشير إلى تاريخ المنتجات القديمة
                    old_product_markers = df[col].apply(lambda x: isinstance(x, str) and any(p in x for p in old_product_date_str))
                
                # تحويل إلى تاريخ ووقت، مع تحويل الأخطاء والقيم None إلى NaT
                df[col] = pd.to_datetime(df[col], errors='coerce')
                
                # إعادة تعيين تاريخ المنتجات القديمة للقيم المحددة
                if col == 'date_production':
                    df.loc[old_product_markers, col] = special_old_product_date
                
                print(f"Processed date column: {col}. Null count after processing: {df[col].isnull().sum()}")


        # 5. (اختياري) تحويل أعمدة أخرى إلى النوع المناسب إذا لزم الأمر
        # مثال: df['garantie'] = df['garantie'].astype(str)

        # طباعة بعض المعلومات لتصحيح الأخطاء
        # print("DataFrame head after loading and cleaning:")
        # print(df.head())
        # print("DataFrame info:")
        # df.info()


        return df, column_mapping # أرجع القاموس أيضًا

    except Exception as e:
        print(f"Error loading or processing file: {e}")
        import traceback
        traceback.print_exc() # طباعة تتبع الخطأ الكامل
        return None, None

# --- دالة حفظ بيانات التدريب ---
def save_training_data(df):
    """
    حفظ بيانات التدريب لاستخدامها لاحقًا في تحسين التحليل.
    يمكن تدريب نموذج التعلم الآلي باستخدام البيانات التي تم تحميلها.
    """
    try:
        # إنشاء مجلد للبيانات المدربة إذا لم يكن موجودًا
        training_folder = "training_data"
        models_folder = "models"
        os.makedirs(training_folder, exist_ok=True)
        os.makedirs(models_folder, exist_ok=True)
        
        # حفظ نسخة من DataFrame للمرجع
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        df_file = os.path.join(training_folder, f"training_data_{timestamp}.pkl")
        df.to_pickle(df_file)
        
        # إذا وجدت بيانات تدريب سابقة، قم بدمجها مع البيانات الجديدة
        training_features_file = os.path.join(models_folder, "training_features.json")
        if os.path.exists(training_features_file):
            with open(training_features_file, 'r', encoding='utf-8') as f:
                training_data = json.load(f)
        else:
            training_data = {
                "file_paths": [],
                "feature_importance": {},
                "training_examples": []
            }
        
        # إضافة مسار الملف الجديد
        training_data["file_paths"].append(df_file)
        
        # استخراج ميزات من البيانات للتدريب
        # هنا يمكننا إضافة أنماط معروفة أو قواعد خاصة بالشركة
        
        # 1. التحقق من الأنماط المتكررة في البيانات (مثل منتج معين يتطلب قطع غيار محددة)
        if 'produit' in df.columns and 'article_consommé' in df.columns:
            produit_parts = df.groupby('produit')['article_consommé'].agg(lambda x: list(x.dropna().unique())).to_dict()
            
            # دمج مع البيانات الموجودة
            if "produit_parts" in training_data["feature_importance"]:
                for produit, parts in produit_parts.items():
                    if produit in training_data["feature_importance"]["produit_parts"]:
                        # إضافة قطع جديدة إلى القائمة الموجودة
                        training_data["feature_importance"]["produit_parts"][produit].extend(parts)
                        # إزالة التكرارات
                        training_data["feature_importance"]["produit_parts"][produit] = list(set(training_data["feature_importance"]["produit_parts"][produit]))
                    else:
                        training_data["feature_importance"]["produit_parts"][produit] = parts
            else:
                training_data["feature_importance"]["produit_parts"] = produit_parts
        
        # 2. حفظ المنتجات القديمة التي تم تمييزها بتاريخ 11-11-2011
        if 'date_production' in df.columns:
            old_product_date = pd.to_datetime('2011-11-11')
            old_products = df[df['date_production'] == old_product_date]['produit'].unique().tolist()
            
            if "old_products" in training_data["feature_importance"]:
                training_data["feature_importance"]["old_products"].extend(old_products)
                training_data["feature_importance"]["old_products"] = list(set(training_data["feature_importance"]["old_products"]))
            else:
                training_data["feature_importance"]["old_products"] = old_products
        
        # 3. حفظ حالات العمود الخاص بالضمان
        if 'garantie' in df.columns:
            garantie_values = df['garantie'].dropna().unique().tolist()
            
            if "garantie_values" in training_data["feature_importance"]:
                training_data["feature_importance"]["garantie_values"].extend(garantie_values)
                training_data["feature_importance"]["garantie_values"] = list(set(training_data["feature_importance"]["garantie_values"]))
            else:
                training_data["feature_importance"]["garantie_values"] = garantie_values
        
        # 4. تدريب نموذج بسيط للكشف عن الأخطاء (إذا كان هناك عمود Error Description)
        if "Error Description" in df.columns and not df["Error Description"].isnull().all():
            # تحضير البيانات للتدريب
            training_examples = []
            
            for idx, row in df.iterrows():
                if pd.notna(row.get("Error Description")) and row.get("Error Description") != "":
                    # هناك بيانات خطأ محددة في هذا الصف
                    example = {
                        "data": row.drop("Error Description").to_dict(),
                        "error": row["Error Description"]
                    }
                    training_examples.append(example)
            
            # إضافة أمثلة التدريب الجديدة
            training_data["training_examples"].extend(training_examples)
            
            # تدريب نموذج بسيط للتنبؤ بوجود أخطاء (مثال: RandomForest)
            train_error_model(df)
        
        # حفظ بيانات التدريب المحدثة
        with open(training_features_file, 'w', encoding='utf-8') as f:
            json.dump(training_data, f, ensure_ascii=False, indent=2)
        
        return True
    
    except Exception as e:
        print(f"Error saving training data: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- دالة تدريب نموذج التعلم الآلي ---
def train_error_model(df):
    """تدريب نموذج للكشف عن الأخطاء في البيانات"""
    try:
        if "Error Description" not in df.columns:
            return False
        
        # إنشاء عمود هدف (وجود خطأ أم لا)
        df['has_error'] = df['Error Description'].apply(lambda x: 0 if pd.isna(x) or x == "" else 1)
        
        # تحضير الميزات
        feature_cols = []
        
        # استخدام الأعمدة الرقمية فقط في البداية (يمكن تحسين هذا لاحقًا)
        for col in df.columns:
            if col not in ['Error Description', 'has_error']:
                if df[col].dtype in [np.number] or pd.api.types.is_datetime64_dtype(df[col]):
                    feature_cols.append(col)
        
        if not feature_cols:
            # لا توجد أعمدة رقمية كافية للتدريب
            return False
        
        # تحضير الميزات والهدف
        X = df[feature_cols].copy()
        y = df['has_error']
        
        # معالجة القيم المفقودة
        X = X.fillna(-1)
        
        # تحويل التواريخ إلى أرقام
        for col in X.columns:
            if pd.api.types.is_datetime64_dtype(X[col]):
                # تحويل التاريخ إلى Unix timestamp
                X[col] = X[col].apply(lambda x: x.timestamp() if not pd.isna(x) else -1)
        
        # حذف التدريب حيث لا تتوفر مكتبة sklearn
        print("Fonctionnalité d'apprentissage automatique désactivée")
        
        # حفظ قائمة الميزات
        models_folder = "models"
        os.makedirs(models_folder, exist_ok=True)
        
        # حفظ قائمة الميزات
        with open(os.path.join(models_folder, "feature_cols.pkl"), 'wb') as f:
            pickle.dump(feature_cols, f)
        
        return True
    
    except Exception as e:
        print(f"Error training model: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- دالة استخدام نموذج مُدرب ---
def use_trained_model(df):
    """استخدام النموذج المدرب للتنبؤ بالأخطاء المحتملة"""
    # Fonctionnalité d'apprentissage automatique désactivée
    print("Fonctionnalité d'apprentissage automatique désactivée")
    return []

# --- دالة تحليل القواعد المحسنة ---
def analyze_dataframe_rules(df):
    """Performs rule-based error checks based on the specific dataset and trained data."""
    errors = []
    required_date_cols = ['date_production', 'date_de_reparation', 'date_reception']

    # S'assurer que les colonnes requises existent
    if not all(col in df.columns for col in required_date_cols):
        print("Analyse des règles de date ignorée en raison de colonnes manquantes.")
        return errors

    # Charger les données d'entraînement si disponibles
    training_features_file = os.path.join("models", "training_features.json")
    training_data = None
    
    if os.path.exists(training_features_file):
        try:
            with open(training_features_file, 'r', encoding='utf-8') as f:
                training_data = json.load(f)
        except Exception as e:
            print(f"Erreur lors du chargement des données d'entraînement: {e}")
    
    # Définir la date 11-11-2011 comme date spéciale pour les produits anciens
    old_product_date = pd.to_datetime('2011-11-11')
    
    # Utiliser les données des produits anciens de l'entraînement si disponibles
    old_products = []
    if training_data and "feature_importance" in training_data and "old_products" in training_data["feature_importance"]:
        old_products = training_data["feature_importance"]["old_products"]
    
    # 1. Vérifier si la date de production est antérieure à la date de réparation
    # Ignorer les lignes avec NaT dans l'une des colonnes
    valid_prod_repair_dates = df.dropna(subset=['date_production', 'date_de_reparation'])
    invalid_prod_after_repair = valid_prod_repair_dates[
        (valid_prod_repair_dates['date_production'] > valid_prod_repair_dates['date_de_reparation']) &
        (valid_prod_repair_dates['date_production'] != old_product_date)  # Exclure la date 11-11-2011
    ]
    for index in invalid_prod_after_repair.index:
        # Ne pas signaler d'erreur si c'est un produit ancien connu des données d'entraînement
        if 'produit' in df.columns and df.loc[index, 'produit'] in old_products:
            continue
            
        errors.append({
            "row_index": index,
            "error_type": "Erreur de date",
            "description": f"Date de production ({df.loc[index, 'date_production']:%Y-%m-%d}) postérieure à la date de réparation ({df.loc[index, 'date_de_reparation']:%Y-%m-%d}). La date de production doit être antérieure à la réparation."
        })

    # 2. Vérifier si la date de réception est antérieure ou égale à la date de réparation
    valid_rec_repair_dates = df.dropna(subset=['date_reception', 'date_de_reparation'])
    invalid_rec_after_repair = valid_rec_repair_dates[
        valid_rec_repair_dates['date_reception'].dt.date > valid_rec_repair_dates['date_de_reparation'].dt.date # Comparer les dates uniquement
    ]
    for index in invalid_rec_after_repair.index:
         errors.append({
            "row_index": index,
            "error_type": "Erreur de date",
            "description": f"Date de réception ({df.loc[index, 'date_reception']:%Y-%m-%d}) postérieure à la date de réparation ({df.loc[index, 'date_de_reparation']:%Y-%m-%d}). La réception doit être antérieure ou le même jour que la réparation."
        })

    # 3. Identifier les dates converties en NaT parce qu'elles sont des placeholders
    for col in ['date_production', 'date_de_reparation', 'date_reception']:
         # Rechercher NaT dans la colonne actuelle qui *n'était pas* NaN à l'origine (si nous avons suivi)
         # Approche simplifiée: supposer que tout NaT peut résulter d'un placeholder ou d'une erreur de conversion réelle
         placeholder_indices = df[df[col].isna()].index
         # Éviter de dupliquer les erreurs si un problème de date a déjà été signalé
         existing_error_indices = {e['row_index'] for e in errors}
         for index in placeholder_indices:
             # Vérifier si la colonne d'origine contenait une valeur (et n'était pas complètement vide)
             # Cela nécessite d'accéder aux données d'origine avant la conversion, ce qui est complexe.
             # Simplification: signaler NaT comme date potentiellement invalide/placeholder.
             if index not in existing_error_indices:
                 # Essayer d'obtenir la valeur originale si possible (peut ne pas toujours fonctionner)
                 original_value = "Unknown" # Placeholder
                 try:
                     # This requires loading the original data again or passing it
                     # For simplicity, we just flag it as potentially invalid
                      pass
                 except:
                     pass

                 # Déterminer le nom de colonne en français
                 col_french_name = ""
                 if col == 'date_production':
                     col_french_name = "Date de production"
                 elif col == 'date_de_reparation':
                     col_french_name = "Date de réparation"
                 elif col == 'date_reception':
                     col_french_name = "Date de réception"

                 # Ne pas signaler d'erreur si la valeur de date est invalide mais que la colonne est la date de production
                 # et qu'il y avait une valeur dans la date de production égale à 11-11-2011 (produit ancien)
                 if col == 'date_production' and 'date_production' in df.columns and not pd.isna(df.loc[index, 'date_production']) and df.loc[index, 'date_production'] == old_product_date:
                     continue
                  
                 # Exception pour les produits anciens connus de l'entraînement
                 if col == 'date_production' and 'produit' in df.columns and df.loc[index, 'produit'] in old_products:
                     continue

                 # Signaler les placeholders potentiels ou erreurs de conversion menant à NaT
                 errors.append({
                     "row_index": index,
                     "error_type": "Date invalide",
                     "description": f"{col_french_name} manquante ou au format incorrect. Veuillez vérifier la date saisie."
                 })


    # 4. Vérifier les relations produit-pièces détachées à l'aide des données d'entraînement
    if training_data and "feature_importance" in training_data and "produit_parts" in training_data["feature_importance"]:
        produit_parts = training_data["feature_importance"]["produit_parts"]
        
        if 'produit' in df.columns and 'article_consommé' in df.columns:
            for index, row in df.iterrows():
                if index in {e['row_index'] for e in errors}:
                    continue  # Éviter de dupliquer les erreurs
                
                produit = row['produit']
                part = row['article_consommé']
                
                # Ignorer les lignes avec pièces détachées vides
                if pd.isna(part) or part == "":
                    continue
                
                # Vérifier la compatibilité produit-pièce détachée
                if produit in produit_parts:
                    valid_parts = produit_parts[produit]
                    
                    # Possibilité de non-correspondance (ne pas utiliser de correspondance exacte)
                    if part not in valid_parts:
                        # Vérification supplémentaire à l'aide de sous-mots
                        match_found = False
                        for valid_part in valid_parts:
                            if isinstance(valid_part, str) and isinstance(part, str):
                                if valid_part.lower() in part.lower() or part.lower() in valid_part.lower():
                                    match_found = True
                                    break
                        
                        if not match_found:
                            errors.append({
                                "row_index": index,
                                "error_type": "Incompatibilité produit-pièce",
                                "description": f"La pièce '{part}' pourrait ne pas être compatible avec le produit '{produit}' selon les données d'entraînement."
                            })

    # 5. (Optionnel) Vérifier si `article_consommé` est manquant
    missing_parts = df[df['article_consommé'].isnull() | (df['article_consommé'] == '')]
    # Vous pourriez ajouter une logique plus complexe ici (par exemple, si symptome suggère un problème)
    for index in missing_parts.index:
         # Éviter de signaler en double si une autre erreur existe déjà
        if index not in {e['row_index'] for e in errors}:
            errors.append({
                "row_index": index,
                "error_type": "Information manquante",
                "description": "Données de pièce consommée (Article Consommé) manquantes ou vides."
            })

    # 6. Utiliser le modèle de machine learning entraîné (s'il existe)
    ml_errors = use_trained_model(df)
    errors.extend(ml_errors)

    print(f"{len(errors)} erreurs potentielles trouvées via les règles et le modèle entraîné.")
    return errors

# --- Fonction de génération de prompt pour Gemini améliorée ---
def generate_ai_prompt(row_data, column_names):
    """Crée un prompt spécifique pour l'API Gemini pour analyser une ligne du rapport de service."""

    # Utiliser les noms nettoyés dans le prompt pour la cohérence du code
    # row_data DEVRAIT contenir les noms de colonnes nettoyés comme clés
    prompt = f"""Analysez la ligne de données de rapport de service suivante pour détecter les incohérences logiques, en tenant compte du contexte français.
    Colonnes du rapport (noms nettoyés utilisés ci-dessous): {', '.join(column_names)}

    Ligne de données (clé: valeur utilisant les noms nettoyés):
    """
    for col, val in row_data.items():
        # Formater les valeurs pour une meilleure lisibilité (particulièrement les dates et NaN)
        formatted_val = val
        if pd.isna(val):
            formatted_val = "MANQUANT/NaT"
        elif isinstance(val, datetime):
            formatted_val = val.strftime('%Y-%m-%d %H:%M:%S')
        prompt += f"- {col}: {formatted_val}\n"

    prompt += """
    Identifiez les erreurs ou incohérences logiques potentielles. Concentrez-vous sur:

    1.  **Plausibilité et logique des dates:**
        *   Est-ce que `date_production` est raisonnablement antérieure à `date_de_reparation`?
        *   Est-ce que `date_reception` est raisonnablement antérieure ou le même jour que `date_de_reparation`?
        *   Y a-t-il des dates manifestement invalides (comme les années 1899, 1753, ou indiquées par MANQUANT/NaT)? Signalez-les spécifiquement si elles n'ont pas été traitées par d'autres vérifications de logique de date.
        *   Remarque: Si `date_production` est 2011-11-11, c'est une date spéciale indiquant un produit ancien et ne doit pas être signalée comme erreur.

    2.  **Incompatibilité produit - pièce consommée (`produit` vs `article_consommé`):**
        *   Est-ce que l'`article_consommé` (pièce consommée ou description d'action) correspond logiquement au `produit`?
        *   **Contexte:**
            *   Les codes `PFTV` / `LED`/`LCD`/`QLED` dans `Produit` sont des téléviseurs. Les pièces comme `DALLE`, `CARTE MERE TV`, `LED` (bandes), `T-CON`, `REPARATION TV` sont attendues.
            *   Les codes `PFML` / `PLASTIQUE`/`SNOW` dans `Produit` sont des machines à laver (ML = Machine à Laver). Les pièces comme `TAMBOUR ML`, `MOTEUR ESSORAGE`, `MINUTERIE`, `POMPE`, `REP. FONCTIONNEMENT ML` sont attendues.
            *   Les codes `PFRF`/`PFCO` / `BCD`/`CF`/`REF` dans `Produit` sont des réfrigérateurs/congélateurs. Les pièces/actions comme `COMPRESSEUR REF`, `CHARGE DE FREON`, `FILTRE REF`, `THERMOSTAT`, `SOUDURE FUITE` sont attendues.
            *   Les codes `PFCL` / `IQA`/`AZAO`/`CLIM`/`ARMOIRE` dans `Produit` sont des climatiseurs. Les actions comme `INSTALATION CLIM`, `CHARGE DE FREON CLIM`, `VERIFICATION DES FUITES` ou pièces comme `COMPRESSEUR CLIM`, `CARTE MERE CLIM` sont attendues.
            *   Les codes `PFIM` / `NEXT`/`VOX`/`I350`/`N30`/`ALL IN ONE` sont des téléphones mobiles/appareils informatiques. Les pièces comme `BATTERIE`, `AFFICHEUR`, `CONNECTEUR CHARGE`, `REPARATION` sont attendues.
            *   Les codes `PFPE`/`PFMO` / `PETRIN`/`MICRO-ONDE` sont des petits électroménagers. Les pièces comme `MOTEUR`, `MINUTERIE`, `ASSIETTE` sont attendues.
        *   Signalez si une pièce semble clairement incorrecte pour le type de produit (par exemple, 'TAMBOUR ML' pour un 'LED TV', ou 'DALLE' pour 'PLASTIQUE 12KG').
        *   Considérez également si l'`article_consommé` est juste une action comme 'CHANGE, ...' ou 'REP. ...' - c'est généralement acceptable si elle est liée au type de produit.

    3.  **Informations manquantes:**
        *   Est-ce que `article_consommé` ou `date_de_reparation` est manquant ou invalide (MANQUANT/NaT) alors que le `symptome` suggère qu'une réparation aurait dû avoir lieu et des pièces consommées? (par exemple, `Symptome` est 'Arrêt total' mais pas d'`article_consommé` ou de `date_de_reparation` valide).

    **Sortie:**
    *   Si des erreurs sont trouvées, fournissez une description brève et claire pour *chaque* erreur distincte identifiée, en mentionnant les colonnes et valeurs spécifiques impliquées. Commencez chaque description d'erreur par "Erreur: ".
    *   Si *aucune erreur logique* n'est trouvée selon les critères ci-dessus, répondez *uniquement* avec l'expression exacte: "Aucune erreur logique trouvée."
    """
    return prompt


# --- fonction de chatbot (pas de changements structurels majeurs) ---
def get_chatbot_response(user_query, chat_history=None):
    """Obtient une réponse de Gemini pour le chatbot."""
    if not model:
        return "L'assistant n'est pas disponible (clé API manquante ou échec de configuration)."

    context = ""
    if chat_history:
         context += "Historique de chat:\n"
         for entry in chat_history[-5:]: # utiliser seulement les 5 derniers messages pour le contexte
              role = "Utilisateur" if entry['role'] == 'user' else "Assistant"
              context += f"{role}: {entry['content']}\n"
         context += "\n---\n"


    prompt = f"""Vous êtes un assistant utile pour une application d'analyse de données Excel. Cette application analyse les rapports de service (comme celui que l'utilisateur a téléchargé) pour détecter les erreurs logiques telles que des dates incorrectes (production vs réparation) et des incompatibilités entre produits (par exemple, TV, machine à laver, réfrigérateur) et pièces détachées/actions consommées.
    {context}
    Question de l'utilisateur: {user_query}

    Veuillez répondre à la question de l'utilisateur clairement et de manière concise en FRANÇAIS. Vous pouvez expliquer:
    - Comment l'application vérifie les erreurs de date (production avant réparation, réception avant réparation, dates placeholders invalides comme 1899/1753).
    - Notez que la date 11-11-2011 est traitée comme un cas spécial indiquant un produit ancien et n'est pas considérée comme une erreur.
    - Comment elle essaie de détecter si une pièce détachée ('Article Consommé') correspond au type de produit ('Produit').
    - Comment interpréter le tableau de résultats, en particulier la colonne 'Error Description'.
    - Conseils généraux sur la qualité des données dans les rapports de service.
    Gardez vos réponses centrées sur les fonctionnalités de l'application et le contexte d'analyse des données.
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Erreur lors de l'appel à l'API Gemini pour le chatbot: {e}")
        import traceback
        traceback.print_exc()
        return f"Désolé, j'ai rencontré une erreur en essayant de répondre: {e}"

# --- Fonction pour l'analyse d'une ligne avec Gemini AI ---
def analyze_row_with_ai(row_index, row_data, column_names):
    """Analyser une ligne individuelle avec l'API Gemini pour détecter des incohérences logiques."""
    if not model:
        return None
    
    try:
        # Créer un prompt spécifique pour cette ligne
        prompt = generate_ai_prompt(row_data, column_names)
        
        # Appeler l'API Gemini
        response = model.generate_content(prompt) # , request_options={'timeout': 120})
        
        # Traiter la réponse
        response_text = response.text.strip()
        
        # Si aucune erreur n'est trouvée, retourner None
        if "Aucune erreur logique trouvée" in response_text:
            return None
        
        # Sinon, formatter et retourner les erreurs trouvées
        return {
            "row_index": row_index,
            "error_type": "Analyse IA",
            "description": response_text.replace("Erreur: ", "")
        }
    
    except Exception as e:
        print(f"Error calling Gemini API for row {row_index}: {e}")
        import traceback
        traceback.print_exc()
        return None