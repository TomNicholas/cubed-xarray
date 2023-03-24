import functools
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypeVar, Union, Tuple, List

import numpy as np

from xarray.core import utils
from xarray.core.parallelcompat import ChunkManagerEntrypoint
from xarray.core.pycompat import is_chunked_array, is_duck_dask_array

T_ChunkedArray = TypeVar("T_ChunkedArray")

# TODO importing TypeAlias is a pain on python 3.9 without typing_extensions in the CI
# T_Chunks: TypeAlias = tuple[tuple[int, ...], ...]
T_Chunks = Any

CHUNK_MANAGERS: dict[str, type["ChunkManagerEntrypoint"]] = {}

if TYPE_CHECKING:
    from xarray.core.types import CubedArray, ZarrArray


class CubedManager(ChunkManagerEntrypoint["CubedArray"]):
    array_cls: type["CubedArray"]

    def __init__(self):
        from cubed import Array

        self.array_cls = Array

    def chunks(self, data: "CubedArray") -> T_Chunks:
        return data.chunks

    def from_array(self, data: np.ndarray, chunks, **kwargs) -> "CubedArray":
        from cubed import Array, from_array

        from xarray.core import indexing

        # cubed-specific kwargs
        spec = kwargs.pop("spec", None)

        if isinstance(data, Array):
            data = data.rechunk(chunks)
        elif is_duck_dask_array(data):
            raise TypeError("Trying to rechunk a dask array using cubed")
        else:
            if isinstance(data, indexing.ExplicitlyIndexed):
                # Unambiguously handle array storage backends (like NetCDF4 and h5py)
                # that can't handle general array indexing. For example, in netCDF4 you
                # can do "outer" indexing along two dimensions independent, which works
                # differently from how NumPy handles it.
                # da.from_array works by using lazy indexing with a tuple of slices.
                # Using OuterIndexer is a pragmatic choice: dask does not yet handle
                # different indexing types in an explicit way:
                # https://github.com/dask/dask/issues/2883
                data = indexing.ImplicitToExplicitIndexingAdapter(
                    data, indexing.OuterIndexer
                )

            if utils.is_dict_like(chunks):
                chunks = tuple(chunks.get(n, s) for n, s in enumerate(data.shape))

            data = from_array(
                data,
                chunks,
                spec=spec,
            )

        return data

    def rechunk(self, data: "CubedArray", chunks, **kwargs) -> "CubedArray":
        return data.rechunk(chunks, **kwargs)

    def compute(self, *data: "CubedArray", **kwargs) -> np.ndarray:
        from cubed import compute

        return compute(*data, **kwargs)

    @property
    def array_api(self) -> Any:
        from cubed import array_api

        return array_api

    def reduction(
        self,
        arr: T_ChunkedArray,
        func: Callable,
        combine_func: Optional[Callable] = None,
        aggregate_func: Optional[Callable] = None,
        axis: Optional[Union[int, Sequence[int]]] = None,
        dtype: Optional[np.dtype] = None,
        keepdims: bool = False,
    ) -> T_ChunkedArray:
        from cubed.core.ops import reduction

        return reduction(
            arr,
            func=func,
            combine_func=combine_func,
            aggegrate_func=aggregate_func,  # TODO fix the typo in argument name in cubed
            axis=axis,
            dtype=dtype,
            keepdims=keepdims,
        )

    def map_blocks(
        self,
        func,
        *args,
        dtype=None,
        chunks=None,
        drop_axis=[],
        new_axis=None,
        **kwargs,
    ):
        from cubed.core.ops import map_blocks

        return map_blocks(
            func,
            *args,
            dtype=dtype,
            chunks=chunks,
            drop_axis=drop_axis,
            new_axis=new_axis,
            **kwargs,
        )

    def blockwise(
        self,
        func,
        out_ind,
        *args: Any,
        # can't type this as mypy assumes args are all same type, but blockwise args alternate types
        dtype=None,
        adjust_chunks=None,
        new_axes=None,
        align_arrays=True,
        target_store=None,
        **kwargs,
    ):
        from cubed.core.ops import blockwise

        # TODO where to get the target_store kwarg from? Filter down from a blockwise call? Set as attribute on CubedManager?

        return blockwise(
            func,
            out_ind,
            *args,
            dtype=dtype,
            adjust_chunks=adjust_chunks,
            new_axes=new_axes,
            align_arrays=align_arrays,
            target_store=target_store,
            **kwargs,
        )

    def apply_gufunc(
        self,
        func,
        signature,
        *args,
        axes=None,
        axis=None,
        keepdims=False,
        output_dtypes=None,
        output_sizes=None,
        vectorize=None,
        allow_rechunk=False,
        meta=None,
        **kwargs,
    ):
        if allow_rechunk:
            raise NotImplementedError(
                "cubed.apply_gufunc doesn't support allow_rechunk"
            )
        if keepdims:
            raise NotImplementedError("cubed.apply_gufunc doesn't support keepdims")

        from cubed import apply_gufunc

        return apply_gufunc(
            func,
            signature,
            *args,
            axes=axes,
            axis=axis,
            output_dtypes=output_dtypes,
            output_sizes=output_sizes,
            vectorize=vectorize,
            **kwargs,
        )

    def unify_chunks(
        self, *args, **kwargs
    ) -> tuple[dict[str, T_Chunks], list["CubedArray"]]:
        from cubed.core import unify_chunks

        return unify_chunks(*args, **kwargs)

    def store(
        self,
        sources: Union["CubedArray", Sequence["CubedArray"]],
        targets: Union["ZarrArray", Sequence["ZarrArray"]],
        **kwargs: dict[str, Any],
    ):
        """Used when writing to any backend."""
        from cubed.core.ops import store

        return store(
            sources,
            targets,
            **kwargs,
        )