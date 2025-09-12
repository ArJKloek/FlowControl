

def read_dde(master, address, dde_or_list):
        """
        Read one or many DDE parameters.
        - If `dde_or_list` is an int: returns the single value or None.
        - If it's an iterable of ints: returns {dde: value_or_None} using a chained read.
        """
        try:
            # ---- multiple DDEs (chained read) ----
            if isinstance(dde_or_list, Iterable) and not isinstance(dde_or_list, (str, bytes)):
                ddes = [int(d) for d in dde_or_list]
                params = []
                for d in ddes:
                    p = master.db.get_parameter(d)
                    p['node'] = address
                    params.append(p)
                res = master.read_parameters(params)  # list of dicts, same order as params
                out = {}
                for d, r in zip(ddes, res or []):
                    out[d] = r.get('data') if r and r.get('status', 1) == 0 else None
                return out

            # ---- single DDE ----
            d = int(dde_or_list)
            p = master.db.get_parameter(d)
            p['node'] = address
            res = master.read_parameters([p])
            if res and res[0].get('status', 1) == 0:
                return res[0]['data']
            return None

        except Exception:
            return None
