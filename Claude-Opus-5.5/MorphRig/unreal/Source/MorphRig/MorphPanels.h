#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Views/SListView.h"

class AMorphShowcaseGameMode;
class AMorphOperative;
class SSearchBox;

struct FMorphBrowserRow
{
	FName Id;
	FString Form;
	float Duration = 0.f;
	int32 Frames = 0;
	FString Notes;
	bool bRequired = true;
	int32 Markers = 0;
};

/** Searchable animation browser: every inventory entry plus extra helper clips. */
class SMorphBrowser : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SMorphBrowser) {}
		SLATE_ARGUMENT(AMorphShowcaseGameMode*, GameMode)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	void FocusSearch();

private:
	void OnFilter(const FText& Text);
	TSharedRef<ITableRow> OnRow(TSharedPtr<FMorphBrowserRow> Item, const TSharedRef<STableViewBase>& Owner);
	void Play(TSharedPtr<FMorphBrowserRow> Item, bool bViewer);

	TWeakObjectPtr<AMorphShowcaseGameMode> GM;
	TArray<TSharedPtr<FMorphBrowserRow>> AllRows;
	TArray<TSharedPtr<FMorphBrowserRow>> Rows;
	TSharedPtr<SListView<TSharedPtr<FMorphBrowserRow>>> List;
	TSharedPtr<SSearchBox> Search;
	bool bLoop = true;
	bool bOnlyRequired = false;
	FString Filter;
};

/** Face control panel: every morph target, every bone-driven face control, expression presets. */
class SMorphFacePanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SMorphFacePanel) {}
		SLATE_ARGUMENT(AMorphOperative*, Operative)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	void ApplyPreset(const FString& Name);
	TWeakObjectPtr<AMorphOperative> Op;
};
