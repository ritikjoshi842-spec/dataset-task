import pandas as pd
import numpy as np
import io
import csv
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, List
import datetime

@dataclass
class ColumnInfo:
    semantic_type: str
    dtype: str
    nunique: int
    null_count: int
    null_pct: float
    sample_values: list

@dataclass
class DataQuality:
    duplicates: int
    total_nulls: int
    high_null_cols: list
    constant_cols: list
    mixed_type_cols: list

@dataclass
class DatasetContext:
    name: str
    df: pd.DataFrame
    schema: Dict[str, ColumnInfo]
    n_rows: int
    n_cols: int
    quality: DataQuality
    fingerprint: str

    def to_llm_schema_summary(self, max_cols=60):
        summary = {
            "name": self.name,
            "rows": self.n_rows,
            "cols": self.n_cols,
            "columns": []
        }
        for i, (col, info) in enumerate(self.schema.items()):
            if i >= max_cols:
                summary["columns"].append({"note": f"... and {self.n_cols - max_cols} more columns"})
                break
            
            col_dict = {
                "name": col,
                "type": info.semantic_type,
                "null_pct": round(info.null_pct, 2)
            }
            if info.semantic_type == "categorical":
                col_dict["samples"] = [str(x) for x in info.sample_values[:5]]
            elif info.semantic_type in ["numeric", "datetime"]:
                col_dict["samples"] = [str(x) for x in info.sample_values]
            
            summary["columns"].append(col_dict)
            
        return summary

def generate_fingerprint(df: pd.DataFrame) -> str:
    hasher = hashlib.md5()
    hasher.update(str(df.shape).encode('utf-8'))
    hasher.update(str(list(df.columns)).encode('utf-8'))
    head_bytes = df.head(10).to_json().encode('utf-8')
    tail_bytes = df.tail(10).to_json().encode('utf-8')
    hasher.update(head_bytes)
    hasher.update(tail_bytes)
    return hasher.hexdigest()

def infer_semantic_type(col_name: str, series: pd.Series, n_rows: int) -> str:
    non_null_s = series.dropna()
    if len(non_null_s) == 0:
        return "text"
    
    nunique = series.nunique(dropna=True)
    unique_ratio = nunique / len(non_null_s) if len(non_null_s) > 0 else 0
    col_name_lower = str(col_name).lower()
    
    if unique_ratio >= 0.95 and any(hint in col_name_lower for hint in ['id', 'uuid', 'guid', 'code', 'hash', 'key']):
        return "id_like"
        
    bool_values = {'true', 'false', 'yes', 'no', 't', 'f', 'y', 'n', '0', '1', '0.0', '1.0'}
    clean_str_vals = set(str(v).lower().strip() for v in non_null_s.unique())
    clean_str_vals.discard('nan')
    clean_str_vals.discard('none')
    clean_str_vals.discard('null')
    if len(clean_str_vals) == 2 and clean_str_vals.issubset(bool_values):
        return "boolean"
            
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    
    if series.dtype == 'object' or pd.api.types.is_string_dtype(series):
        sample_size = min(1000, len(non_null_s))
        s_sample = non_null_s.sample(sample_size, random_state=42) if len(non_null_s) > 1000 else non_null_s
        
        is_pure_int = s_sample.astype(str).str.match(r'^\d+$').all()
        if not is_pure_int or any(hint in col_name_lower for hint in ['date', 'time', 'year', 'month', 'day']):
            try:
                parsed_dates = pd.to_datetime(s_sample, errors='coerce')
                valid_ratio = parsed_dates.notna().mean()
                if valid_ratio < 0.80:
                    parsed_dates = pd.to_datetime(s_sample, errors='coerce', dayfirst=True)
                    valid_ratio = parsed_dates.notna().mean()
                if valid_ratio >= 0.80:
                    return "datetime"
            except:
                pass
                
    if pd.api.types.is_numeric_dtype(series):
        if unique_ratio >= 0.95 and any(hint in col_name_lower for hint in ['id', 'num']):
             return "id_like"
        return "numeric"
        
    if series.dtype == 'object' or pd.api.types.is_string_dtype(series):
        cleaned = series.astype(str).str.replace(r'[\,\$₹\%\s]', '', regex=True)
        cleaned = cleaned.replace(['', 'nan', 'NaN', 'null', 'Null', 'none', 'None', '-', 'N/A', 'n/a'], np.nan)
        cleaned_non_null = cleaned.dropna()
        
        if len(cleaned_non_null) > 0:
            sample_size = min(1000, len(cleaned_non_null))
            c_sample = cleaned_non_null.sample(sample_size, random_state=42) if len(cleaned_non_null) > 1000 else cleaned_non_null
            
            parsed_nums = pd.to_numeric(c_sample, errors='coerce')
            valid_ratio = parsed_nums.notna().mean()
            if valid_ratio >= 0.85:
                return "numeric"
            
    max_cat_size = max(50, int(0.05 * n_rows))
    if nunique <= max_cat_size:
        return "categorical"
        
    return "text"

def clean_and_profile_dataset(name: str, df: pd.DataFrame) -> DatasetContext:
    df.columns = df.columns.astype(str).str.strip()
    
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    
    df.dropna(how='all', axis=1, inplace=True)
    df.dropna(how='all', axis=0, inplace=True)
    
    n_rows, n_cols = df.shape
    
    schema = {}
    total_nulls = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum())
    high_null_cols = []
    constant_cols = []
    mixed_type_cols = []
    
    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        null_pct = (null_count / n_rows) * 100 if n_rows > 0 else 0
        nunique = int(series.nunique(dropna=True))
        
        if null_pct > 50:
            high_null_cols.append(col)
        if nunique == 1:
            constant_cols.append(col)
            
        sem_type = infer_semantic_type(col, series, n_rows)
        
        if sem_type == 'numeric' and not pd.api.types.is_numeric_dtype(series):
            cleaned = series.astype(str).str.replace(r'[\,\$₹\%\s]', '', regex=True)
            df[col] = pd.to_numeric(cleaned, errors='coerce')
        elif sem_type == 'datetime' and not pd.api.types.is_datetime64_any_dtype(series):
            parsed_dt = pd.to_datetime(series, errors='coerce')
            if parsed_dt.isna().mean() > 0.5:
                parsed_dt = pd.to_datetime(series, errors='coerce', dayfirst=True)
            df[col] = parsed_dt
            
        sample_values = []
        if sem_type in ['numeric', 'datetime']:
            if nunique > 0:
                s_min = df[col].min()
                s_max = df[col].max()
                sample_values = [s_min, s_max]
        elif sem_type == 'categorical':
            val_counts = df[col].value_counts()
            sample_values = val_counts.index[:5].tolist()
        elif sem_type == 'text':
            sample_values = df[col].dropna().head(3).tolist()
            
        schema[col] = ColumnInfo(
            semantic_type=sem_type,
            dtype=str(df[col].dtype),
            nunique=nunique,
            null_count=null_count,
            null_pct=null_pct,
            sample_values=sample_values
        )
        
    quality = DataQuality(
        duplicates=duplicates,
        total_nulls=total_nulls,
        high_null_cols=high_null_cols,
        constant_cols=constant_cols,
        mixed_type_cols=mixed_type_cols
    )
    
    return DatasetContext(
        name=name,
        df=df,
        schema=schema,
        n_rows=n_rows,
        n_cols=n_cols,
        quality=quality,
        fingerprint=generate_fingerprint(df)
    )

def load_dataset_from_bytes(name: str, file_bytes: bytes, extension: str, sheet_name: str = None) -> DatasetContext:
    if extension == 'csv':
        try:
            content = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode('utf-8-sig')
            except UnicodeDecodeError:
                content = file_bytes.decode('latin-1')
                
        try:
            sample = content[:4096]
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
            sep = dialect.delimiter
        except:
            sep = None
            
        df = pd.read_csv(io.StringIO(content), sep=sep, engine="python")
    elif extension in ['xlsx', 'xls']:
        if sheet_name:
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        raise ValueError(f"Unsupported extension: {extension}")
        
    return clean_and_profile_dataset(name, df)
